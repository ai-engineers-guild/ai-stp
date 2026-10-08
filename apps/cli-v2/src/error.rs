use serde_json::{Value, json};

pub type Result<T> = std::result::Result<T, Failure>;

#[derive(Debug)]
pub struct Failure {
    pub kind: ErrorKind,
    pub message: String,
}

#[derive(Clone, Copy, Debug)]
pub enum ErrorKind {
    Input,
    NotFound,
    Precondition,
    Conflict,
    Internal,
}

impl ErrorKind {
    pub const ALL: [Self; 5] = [
        Self::Input,
        Self::NotFound,
        Self::Precondition,
        Self::Conflict,
        Self::Internal,
    ];

    pub fn code(self) -> &'static str {
        match self {
            Self::Input => "AI_STP_VALIDATION_ERROR",
            Self::NotFound => "AI_STP_NOT_FOUND",
            Self::Precondition => "AI_STP_PRECONDITION_FAILED",
            Self::Conflict => "AI_STP_CONFLICT",
            Self::Internal => "AI_STP_INTERNAL",
        }
    }

    pub fn exit_code(self) -> u8 {
        match self {
            Self::Input | Self::NotFound => 2,
            Self::Precondition | Self::Conflict => 4,
            Self::Internal => 70,
        }
    }

    pub fn descriptor(self) -> Value {
        let (handling, description) = match self {
            Self::Input => (
                "correct_request",
                "The invocation or input document is invalid.",
            ),
            Self::NotFound => ("correct_request", "The requested object does not exist."),
            Self::Precondition | Self::Conflict => (
                "reconcile_state",
                "The input does not satisfy the operation's preconditions.",
            ),
            Self::Internal => ("report_bug", "An unexpected internal failure occurred."),
        };
        json!({"code": self.code(), "exit_class": self.exit_code(), "handling": handling, "description": description})
    }
}

impl Failure {
    pub fn new(kind: ErrorKind, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
        }
    }

    pub fn input(message: impl Into<String>) -> Self {
        Self::new(ErrorKind::Input, message)
    }

    pub fn precondition(message: impl Into<String>) -> Self {
        Self::new(ErrorKind::Precondition, message)
    }
}

impl std::fmt::Display for Failure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.kind.code(), self.message)
    }
}

impl std::error::Error for Failure {}
