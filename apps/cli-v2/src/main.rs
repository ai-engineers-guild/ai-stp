use std::{
    io::{self, Write},
    process::ExitCode,
};

fn main() -> ExitCode {
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
