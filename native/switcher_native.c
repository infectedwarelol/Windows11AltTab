#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <cpuid.h>

#define HOOK_MESSAGE (WM_APP + 1)
#define CAPTURE_MESSAGE (WM_APP + 2)
#define INJECTED_TAG ((ULONG_PTR)0x504C414EUL)
#define STALE_HEARTBEAT_MS 3000ULL
#define MASK_KEY 0xE8
#define REHOOK_INTERVAL_MS 5000

enum {
    EVENT_TAB_FORWARD = 1,
    EVENT_TAB_BACKWARD = 2,
    EVENT_ALT_RELEASED = 3,
    EVENT_ESCAPE = 4,
    EVENT_CONFIRM = 5,
    EVENT_PREVIOUS = 6,
    EVENT_NEXT = 7,
    EVENT_WHEEL = 8,
};

static HWND target_window;
static HANDLE hook_thread;
static DWORD hook_thread_id;
static HANDLE hook_ready;
static volatile LONG hook_installed;
static HMODULE hook_module;
static HHOOK keyboard_hook;
static HHOOK mouse_hook;
static volatile LONG capture_keys;
static volatile LONG64 heartbeat_tick;
static int left_alt, right_alt, left_shift, right_shift, control_down, windows_down;
static int session_open;
static int tab_swallowed;
static int captured_down[256];

static int key_held(int virtual_key)
{
    return (GetAsyncKeyState(virtual_key) & 0x8000) != 0;
}

static void send_mask_key(void)
{
    INPUT inputs[2];
    ZeroMemory(inputs, sizeof(inputs));
    for (int index = 0; index < 2; index++) {
        inputs[index].type = INPUT_KEYBOARD;
        inputs[index].ki.wVk = MASK_KEY;
        inputs[index].ki.dwExtraInfo = INJECTED_TAG;
    }
    inputs[1].ki.dwFlags = KEYEVENTF_KEYUP;
    SendInput(2, inputs, sizeof(INPUT));
}

static void post_event(int event)
{
    PostMessageW(target_window, HOOK_MESSAGE, (WPARAM)event, 0);
}

static void sync_modifiers(void)
{
    left_alt = key_held(VK_LMENU);
    right_alt = key_held(VK_RMENU);
    left_shift = key_held(VK_LSHIFT);
    right_shift = key_held(VK_RSHIFT);
    control_down = key_held(VK_CONTROL);
    windows_down = key_held(VK_LWIN) || key_held(VK_RWIN);
}

static int is_modifier(DWORD virtual_key)
{
    switch (virtual_key) {
    case VK_MENU: case VK_LMENU: case VK_RMENU:
    case VK_SHIFT: case VK_LSHIFT: case VK_RSHIFT:
    case VK_CONTROL: case VK_LCONTROL: case VK_RCONTROL:
    case VK_LWIN: case VK_RWIN:
        return 1;
    default:
        return 0;
    }
}

static void track_modifier(DWORD virtual_key, int down)
{
    switch (virtual_key) {
    case VK_LMENU: left_alt = down; break;
    case VK_RMENU: right_alt = down; break;
    case VK_MENU: left_alt = down; right_alt = down && right_alt; break;
    case VK_LSHIFT: left_shift = down; break;
    case VK_RSHIFT: right_shift = down; break;
    case VK_SHIFT: left_shift = down; right_shift = down && right_shift; break;
    case VK_CONTROL: case VK_LCONTROL: case VK_RCONTROL: control_down = down; break;
    case VK_LWIN: case VK_RWIN: windows_down = down; break;
    default: break;
    }
}

static int captured_event(DWORD virtual_key)
{
    switch (virtual_key) {
    case VK_ESCAPE: return EVENT_ESCAPE;
    case VK_RETURN: case VK_SPACE: return EVENT_CONFIRM;
    case VK_LEFT: case VK_UP: return EVENT_PREVIOUS;
    case VK_RIGHT: case VK_DOWN: return EVENT_NEXT;
    default: return 0;
    }
}

static int owner_alive(void)
{
    ULONGLONG last = (ULONGLONG)InterlockedCompareExchange64(&heartbeat_tick, 0, 0);
    return GetTickCount64() - last < STALE_HEARTBEAT_MS && IsWindow(target_window);
}

static LRESULT CALLBACK keyboard_proc(int code, WPARAM message, LPARAM data)
{
    if (code != HC_ACTION) {
        return CallNextHookEx(NULL, code, message, data);
    }
    const KBDLLHOOKSTRUCT *key = (const KBDLLHOOKSTRUCT *)data;
    DWORD virtual_key = key->vkCode;
    int down = message == WM_KEYDOWN || message == WM_SYSKEYDOWN;
    if (key->dwExtraInfo == INJECTED_TAG) {
        return CallNextHookEx(NULL, code, message, data);
    }
    if (is_modifier(virtual_key)) {
        int alt_was_down = left_alt || right_alt;
        track_modifier(virtual_key, down);
        if (alt_was_down && !left_alt && !right_alt && session_open) {
            session_open = 0;
            post_event(EVENT_ALT_RELEASED);
        }
        return CallNextHookEx(NULL, code, message, data);
    }
    if (!owner_alive()) {
        session_open = 0;
        tab_swallowed = 0;
        return CallNextHookEx(NULL, code, message, data);
    }
    if (virtual_key == VK_TAB) {
        if (down && (left_alt || right_alt) && !control_down && !windows_down) {
            if (!session_open) {
                session_open = 1;
                send_mask_key();
            }
            tab_swallowed = 1;
            post_event(left_shift || right_shift ? EVENT_TAB_BACKWARD : EVENT_TAB_FORWARD);
            return 1;
        }
        if (!down && tab_swallowed) {
            tab_swallowed = 0;
            return 1;
        }
    }
    if (virtual_key < 256 && InterlockedCompareExchange(&capture_keys, 0, 0)) {
        if (down) {
            captured_down[virtual_key] = 1;
            int event = captured_event(virtual_key);
            if (event) {
                post_event(event);
            }
            return 1;
        }
        if (captured_down[virtual_key]) {
            captured_down[virtual_key] = 0;
            return 1;
        }
    }
    if (virtual_key < 256 && !down && captured_down[virtual_key]) {
        captured_down[virtual_key] = 0;
        return 1;
    }
    return CallNextHookEx(NULL, code, message, data);
}

static LRESULT CALLBACK mouse_proc(int code, WPARAM message, LPARAM data)
{
    if (code != HC_ACTION || message != WM_MOUSEWHEEL || !InterlockedCompareExchange(&capture_keys, 0, 0) || !owner_alive()) {
        return CallNextHookEx(NULL, code, message, data);
    }
    const MSLLHOOKSTRUCT *mouse = (const MSLLHOOKSTRUCT *)data;
    if (mouse->dwExtraInfo == INJECTED_TAG) {
        return CallNextHookEx(NULL, code, message, data);
    }
    PostMessageW(target_window, HOOK_MESSAGE, (WPARAM)EVENT_WHEEL, (LPARAM)(SHORT)HIWORD(mouse->mouseData));
    return 1;
}

static void install_keyboard_hook(void)
{
    if (keyboard_hook) {
        UnhookWindowsHookEx(keyboard_hook);
    }
    if (!session_open) {
        sync_modifiers();
    }
    keyboard_hook = SetWindowsHookExW(WH_KEYBOARD_LL, keyboard_proc, hook_module, 0);
    InterlockedExchange(&hook_installed, keyboard_hook != NULL);
}

static void remove_mouse_hook(void)
{
    if (mouse_hook) {
        UnhookWindowsHookEx(mouse_hook);
        mouse_hook = NULL;
    }
}

static void install_mouse_hook(void)
{
    remove_mouse_hook();
    mouse_hook = SetWindowsHookExW(WH_MOUSE_LL, mouse_proc, hook_module, 0);
}

static DWORD WINAPI hook_main(LPVOID unused)
{
    (void)unused;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCWSTR)(void *)keyboard_proc, &hook_module);
    MSG message;
    PeekMessageW(&message, NULL, WM_USER, WM_USER, PM_NOREMOVE);
    install_keyboard_hook();
    SetEvent(hook_ready);
    if (!keyboard_hook) {
        return 1;
    }
    UINT_PTR rehook_timer = SetTimer(NULL, 0, REHOOK_INTERVAL_MS, NULL);
    while (GetMessageW(&message, NULL, 0, 0) > 0) {
        if (message.hwnd == NULL && message.message == CAPTURE_MESSAGE) {
            if (message.wParam) {
                install_mouse_hook();
            } else {
                remove_mouse_hook();
            }
            continue;
        }
        if (message.hwnd == NULL && message.message == WM_TIMER && message.wParam == rehook_timer) {
            if (!InterlockedCompareExchange(&capture_keys, 0, 0)) {
                remove_mouse_hook();
                install_keyboard_hook();
            }
            continue;
        }
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }
    if (rehook_timer) {
        KillTimer(NULL, rehook_timer);
    }
    remove_mouse_hook();
    if (keyboard_hook) {
        UnhookWindowsHookEx(keyboard_hook);
        keyboard_hook = NULL;
    }
    InterlockedExchange(&hook_installed, 0);
    return 0;
}

__declspec(dllexport) void hook_heartbeat(void)
{
    InterlockedExchange64(&heartbeat_tick, (LONG64)GetTickCount64());
}

__declspec(dllexport) int hook_start(HWND window)
{
    if (hook_thread) {
        return InterlockedCompareExchange(&hook_installed, 0, 0) ? 0 : -1;
    }
    target_window = window;
    hook_heartbeat();
    hook_ready = CreateEventW(NULL, TRUE, FALSE, NULL);
    if (!hook_ready) {
        return -2;
    }
    hook_thread = CreateThread(NULL, 0, hook_main, NULL, 0, &hook_thread_id);
    if (!hook_thread) {
        CloseHandle(hook_ready);
        hook_ready = NULL;
        return -3;
    }
    SetThreadPriority(hook_thread, THREAD_PRIORITY_TIME_CRITICAL);
    WaitForSingleObject(hook_ready, 5000);
    return InterlockedCompareExchange(&hook_installed, 0, 0) ? 0 : -1;
}

__declspec(dllexport) void hook_stop(void)
{
    if (!hook_thread) {
        return;
    }
    PostThreadMessageW(hook_thread_id, WM_QUIT, 0, 0);
    WaitForSingleObject(hook_thread, 2000);
    CloseHandle(hook_thread);
    CloseHandle(hook_ready);
    hook_thread = NULL;
    hook_ready = NULL;
    hook_thread_id = 0;
}

__declspec(dllexport) void hook_set_capture(int enabled)
{
    InterlockedExchange(&capture_keys, enabled != 0);
    if (hook_thread_id) {
        PostThreadMessageW(hook_thread_id, CAPTURE_MESSAGE, (WPARAM)(enabled != 0), 0);
    }
}

__declspec(dllexport) int hook_alt_held(void)
{
    return key_held(VK_MENU);
}

__declspec(dllexport) void unlock_foreground(void)
{
    send_mask_key();
}

__declspec(dllexport) int cpu_supports_avx2_fma(void)
{
    unsigned int eax, ebx, ecx, edx;
    if (!__get_cpuid(1, &eax, &ebx, &ecx, &edx)) {
        return 0;
    }
    const unsigned int fma = 1u << 12, osxsave = 1u << 27, avx = 1u << 28;
    if ((ecx & (fma | osxsave | avx)) != (fma | osxsave | avx)) {
        return 0;
    }
    unsigned int xcr0_low, xcr0_high;
    __asm__ volatile ("xgetbv" : "=a"(xcr0_low), "=d"(xcr0_high) : "c"(0));
    (void)xcr0_high;
    if ((xcr0_low & 0x6u) != 0x6u) {
        return 0;
    }
    if (!__get_cpuid_count(7, 0, &eax, &ebx, &ecx, &edx)) {
        return 0;
    }
    return (ebx & (1u << 5)) != 0;
}
