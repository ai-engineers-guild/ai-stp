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

    public static bool KeyboardFocusOwned(IntPtr window)
    {
        uint process;
        uint thread = GetWindowThreadProcessId(window, out process);
        var info = new GuiThreadInfo { Size = (uint)Marshal.SizeOf(typeof(GuiThreadInfo)) };
        if (thread == 0 || !GetGUIThreadInfo(thread, ref info))
            throw new InvalidOperationException("Native keyboard focus could not be observed");
        return info.Focus != IntPtr.Zero && (info.Focus == window || IsChild(window, info.Focus));
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
