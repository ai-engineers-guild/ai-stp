use std::{
    io::{self, Write},
    process::ExitCode,
};

fn main() -> ExitCode {
    #[cfg(target_os = "linux")]
    {
        let arguments: Vec<_> = std::env::args_os().skip(1).collect();
        if arguments
            .first()
            .is_some_and(|value| value == ai_stp_cli_v2::provider::runtime::entry::FLAG)
        {
            let _ = ai_stp_cli_v2::provider::runtime::entry::run(&arguments[1..]);
            return ExitCode::from(70);
        }
        if arguments
            .first()
            .is_some_and(|value| value == ai_stp_cli_v2::provider::runtime::probe::FLAG)
        {
            return match ai_stp_cli_v2::provider::runtime::probe::run(&arguments[1..]) {
                Ok(report) => {
                    if writeln!(io::stdout().lock(), "{report}").is_ok() {
                        ExitCode::SUCCESS
                    } else {
                        ExitCode::from(70)
                    }
                }
                Err(_) => ExitCode::from(2),
            };
        }
    }
    let invocation = ai_stp_cli_v2::invoke(std::env::args_os());
    let code = invocation.exit_code();
    let write = if invocation.machine {
        writeln!(io::stdout().lock(), "{}", invocation.envelope())
    } else if let Some(text) = invocation.text {
        write!(io::stdout().lock(), "{text}")
    } else {
        match invocation.result {
            Ok(data) => writeln!(io::stdout().lock(), "{data:#}"),
            Err(failure) => writeln!(io::stderr().lock(), "{failure}"),
        }
    };
    match write {
        Ok(()) => ExitCode::from(code),
        Err(error) if error.kind() == io::ErrorKind::BrokenPipe => ExitCode::SUCCESS,
        Err(_) => ExitCode::from(70),
    }
}
