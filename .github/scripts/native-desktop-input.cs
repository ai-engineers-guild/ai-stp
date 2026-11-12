using System;
using System.Runtime.InteropServices;

public static class NativeDesktopInput
{
    [StructLayout(LayoutKind.Sequential)]
    public struct KeyboardInput
    {
        public ushort VirtualKey, ScanCode;
        public uint Flags, Time;
        public UIntPtr ExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct MouseInput
    {
        public int X, Y;
        public uint Data, Flags, Time;
        public UIntPtr ExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct HardwareInput
    {
        public uint Message;
        public ushort Low, High;
    }

    [StructLayout(LayoutKind.Explicit)]
    public struct InputPayload
    {
        [FieldOffset(0)] public KeyboardInput Keyboard;
        [FieldOffset(0)] public MouseInput Mouse;
        [FieldOffset(0)] public HardwareInput Hardware;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct Input
    {
        public uint Type;
        public InputPayload Payload;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Rectangle
    {
        public int Left, Top, Right, Bottom;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Point
    {
        public int X, Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct GuiThreadInfo
    {
        public uint Size, Flags;
        public IntPtr Active, Focus, Capture, MenuOwner, MoveSize, Caret;
        public Rectangle CaretBounds;
    }

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetForegroundWindow(IntPtr window);

    [DllImport("user32.dll")]
    private static extern short GetAsyncKeyState(int key);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetGUIThreadInfo(uint thread, ref GuiThreadInfo info);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsChild(IntPtr parent, IntPtr window);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint count, Input[] inputs, int size);

    [DllImport("user32.dll", EntryPoint = "MapVirtualKeyW")]
    private static extern uint MapVirtualKey(uint code, uint kind);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetPhysicalCursorPos(int x, int y);

    [DllImport("user32.dll")]
    private static extern IntPtr WindowFromPhysicalPoint(Point point);

    [StructLayout(LayoutKind.Sequential)]
    private struct MonitorInfo
    {
        public uint Size;
        public Rectangle Monitor, WorkArea;
        public uint Flags;
    }

    [DllImport("user32.dll")]
    private static extern IntPtr MonitorFromWindow(IntPtr window, uint flags);

    [DllImport("user32.dll", EntryPoint = "GetMonitorInfoW", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetMonitorInfo(IntPtr monitor, ref MonitorInfo info);

    [DllImport("dwmapi.dll")]
    private static extern int DwmGetWindowAttribute(
        IntPtr window, uint attribute, out Rectangle value, uint size);

    public static int[] WorkArea(IntPtr window)
    {
        var info = new MonitorInfo { Size = (uint)Marshal.SizeOf(typeof(MonitorInfo)) };
        if (window == IntPtr.Zero ||
            !GetMonitorInfo(MonitorFromWindow(window, 2), ref info) ||
            info.WorkArea.Right <= info.WorkArea.Left || info.WorkArea.Bottom <= info.WorkArea.Top)
            throw new InvalidOperationException("Native display work area could not be observed");
        return new[] { info.WorkArea.Left, info.WorkArea.Top, info.WorkArea.Right, info.WorkArea.Bottom };
    }

    public static bool WindowFitsWorkArea(IntPtr window)
    {
        Rectangle bounds;
        // DWMWA_EXTENDED_FRAME_BOUNDS excludes invisible resize borders and uses physical pixels.
        if (DwmGetWindowAttribute(window, 9, out bounds, (uint)Marshal.SizeOf(typeof(Rectangle))) != 0)
            throw new InvalidOperationException("Visible native window bounds could not be observed");
        int[] area = WorkArea(window);
        return bounds.Right > bounds.Left && bounds.Bottom > bounds.Top &&
            bounds.Left >= area[0] && bounds.Top >= area[1] &&
            bounds.Right <= area[2] && bounds.Bottom <= area[3];
    }

    private static bool WindowOwnedBy(IntPtr root, IntPtr window)
    {
        return root != IntPtr.Zero && window != IntPtr.Zero &&
            (window == root || IsChild(root, window));
    }

    public static bool PointerButtonsReleased()
    {
        int[] buttons = { 0x01, 0x02, 0x04, 0x05, 0x06 };
        foreach (int button in buttons)
            if ((GetAsyncKeyState(button) & 0x8000) != 0)
                return false;
        return true;
    }

    public static uint ClickAt(IntPtr root, int x, int y)
    {
        if (!WindowOwnedBy(root, GetForegroundWindow()) || PressedModifiers() != 0 ||
            !PointerButtonsReleased() ||
            !SetPhysicalCursorPos(x, y) ||
            !WindowOwnedBy(root, WindowFromPhysicalPoint(new Point { X = x, Y = y })))
            throw new InvalidOperationException("Native pointer has no owned target");
        return Send(new[] {
            new Input { Payload = new InputPayload { Mouse = new MouseInput { Flags = 0x02 } } },
            new Input { Payload = new InputPayload { Mouse = new MouseInput { Flags = 0x04 } } }
        });
    }

    public static uint PressedModifiers()
    {
        int[] keys = { 0x10, 0x11, 0x12, 0x5b, 0x5c };
        uint pressed = 0;
        for (int i = 0; i < keys.Length; i++)
            if ((GetAsyncKeyState(keys[i]) & 0x8000) != 0)
                pressed |= 1u << i;
        return pressed;
    }

    private static GuiThreadInfo KeyboardInfo(IntPtr window)
    {
        uint process;
        uint thread = GetWindowThreadProcessId(window, out process);
        var info = new GuiThreadInfo { Size = (uint)Marshal.SizeOf(typeof(GuiThreadInfo)) };
        if (thread == 0 || !GetGUIThreadInfo(thread, ref info))
            throw new InvalidOperationException("Native keyboard focus could not be observed");
        return info;
    }

    public static bool KeyboardFocusOwned(IntPtr window)
    {
        IntPtr focus = KeyboardInfo(window).Focus;
        return focus != IntPtr.Zero && (focus == window || IsChild(window, focus));
    }

    public static bool KeyboardFocusIsRoot(IntPtr window)
    {
        return KeyboardInfo(window).Focus == window;
    }

    private static Input Key(ushort virtualKey, ushort scan, uint flags)
    {
        return new Input {
            Type = 1,
            Payload = new InputPayload {
                Keyboard = new KeyboardInput { VirtualKey = virtualKey, ScanCode = scan, Flags = flags }
            }
        };
    }

    private static uint Send(Input[] inputs)
    {
        // The caller separately observes the resulting UI value after acknowledged insertion.
        uint accepted = SendInput((uint)inputs.Length, inputs, Marshal.SizeOf(typeof(Input)));
        if (accepted != inputs.Length)
            throw new InvalidOperationException(
                "Native keyboard accepted " + accepted + "/" + inputs.Length +
                " events; Win32=" + Marshal.GetLastWin32Error());
        return accepted;
    }

    private static Input Physical(ushort virtualKey, bool up)
    {
        uint mapped = MapVirtualKey(virtualKey, 4);
        uint prefix = mapped & 0xff00;
        if (mapped == 0 || (prefix != 0 && prefix != 0xe000) || mapped > 0xffff)
            throw new InvalidOperationException("Native key has no supported physical scan code");
        ushort scan = (ushort)(mapped & 0xff);
        uint flags = 0x08u | (prefix == 0xe000 ? 0x01u : 0u) | (up ? 0x02u : 0u);
        return Key(0, scan, flags);
    }

    public static uint Backspace()
    {
        return Send(new[] { Physical(0x08, false), Physical(0x08, true) });
    }

    public static uint Enter()
    {
        return Send(new[] { Physical(0x0d, false), Physical(0x0d, true) });
    }

    public static uint PreviousTab()
    {
        return Send(new[] {
            Physical(0x10, false), Physical(0x09, false),
            Physical(0x09, true), Physical(0x10, true)
        });
    }

    public static uint SelectAll()
    {
        return Send(new[] {
            Physical(0x11, false), Physical(0x41, false),
            Physical(0x41, true), Physical(0x11, true)
        });
    }

    public static uint TypeText(string value)
    {
        if (String.IsNullOrEmpty(value) || value.Length > 120)
            throw new InvalidOperationException("Unexpected native text length");
        var inputs = new Input[value.Length * 2];
        for (int i = 0; i < value.Length; i++)
        {
            inputs[i * 2] = Key(0, value[i], 0x04);
            inputs[i * 2 + 1] = Key(0, value[i], 0x06);
        }
        return Send(inputs);
    }
}
