//! Startup geometry after the configured webview and restored state are attached.

use tauri::{LogicalSize, Manager, PhysicalPosition, PhysicalSize, Runtime, WebviewWindow};

pub(super) fn fit_after_restore<R: Runtime>(window: WebviewWindow<R>) {
    let fit = move || {
        if fit_normal_window(&window).is_err() {
            eprintln!("Could not fit the Desktop window inside the display work area");
        }
    };
    // Tao enqueues AppKit restoration with dispatch_async even on the main thread.
    // Submit after it to the same FIFO queue, rather than racing it through Tao events.
    #[cfg(target_os = "macos")]
    dispatch2::DispatchQueue::main().exec_async(fit);
    #[cfg(not(target_os = "macos"))]
    drop(tauri::async_runtime::spawn_blocking(fit));
}

fn fit_normal_window<R: Runtime>(window: &WebviewWindow<R>) -> tauri::Result<()> {
    if window.is_maximized()? || window.is_fullscreen()? {
        return Ok(());
    }
    let monitor = match window.current_monitor()? {
        Some(monitor) => Some(monitor),
        None => window.primary_monitor()?,
    };
    let Some(monitor) = monitor else {
        return Ok(());
    };
    let area = monitor.work_area();
    if area.size.width == 0 || area.size.height == 0 {
        return Ok(());
    }
    let inner = window.inner_size()?;
    let outer = window.outer_size()?;
    let frame = PhysicalSize::new(
        outer.width.saturating_sub(inner.width),
        outer.height.saturating_sub(inner.height),
    );
    let available = PhysicalSize::new(
        area.size.width.saturating_sub(frame.width).max(1),
        area.size.height.saturating_sub(frame.height).max(1),
    );
    if let Some(configuration) = window
        .app_handle()
        .config()
        .app
        .windows
        .iter()
        .find(|configuration| configuration.label == window.label())
    {
        let minimum = LogicalSize::new(
            configuration.min_width.unwrap_or_default(),
            configuration.min_height.unwrap_or_default(),
        )
        .to_physical::<u32>(window.scale_factor()?);
        if minimum.width > available.width || minimum.height > available.height {
            window.set_min_size(Some(PhysicalSize::new(
                minimum.width.min(available.width),
                minimum.height.min(available.height),
            )))?;
        }
    }
    let size = PhysicalSize::new(
        inner.width.min(available.width),
        inner.height.min(available.height),
    );
    if size != inner {
        window.set_size(size)?;
    }
    let position = window.outer_position()?;
    let fit = PhysicalPosition::new(
        fit_axis(
            position.x,
            area.position.x,
            area.size.width,
            size.width.saturating_add(frame.width),
        ),
        fit_axis(
            position.y,
            area.position.y,
            area.size.height,
            size.height.saturating_add(frame.height),
        ),
    );
    if fit != position {
        window.set_position(fit)?;
    }
    Ok(())
}

fn fit_axis(position: i32, start: i32, available: u32, extent: u32) -> i32 {
    position.clamp(
        start,
        start.saturating_add_unsigned(available.saturating_sub(extent)),
    )
}

#[cfg(test)]
mod tests {
    use super::fit_axis;

    #[test]
    fn retains_fitting_positions_on_a_negative_origin_monitor() {
        assert_eq!(fit_axis(-1500, -1920, 1920, 1200), -1500);
        assert_eq!(fit_axis(-100, -1920, 1920, 1200), -1200);
        assert_eq!(fit_axis(-2500, -1920, 1920, 1200), -1920);
    }

    #[test]
    fn positions_include_the_native_frame_and_work_area_offset() {
        assert_eq!(fit_axis(200, 40, 1000, 1016), 40);
        assert_eq!(fit_axis(200, 40, 1000, 816), 200);
        assert_eq!(fit_axis(500, 40, 1000, 816), 224);
    }

    #[test]
    fn display_coordinate_extremes_do_not_wrap_or_invert_the_range() {
        assert_eq!(fit_axis(i32::MAX, i32::MIN, 640, 300), i32::MIN + 340);
        assert_eq!(fit_axis(i32::MAX, i32::MAX - 20, 640, 300), i32::MAX);
    }
}
