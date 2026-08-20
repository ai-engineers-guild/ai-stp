const rawPaths = process.env.AI_STP_COMPILED_CONTENT_PATHS ?? "";

export const COMPILED_CONTENT_PATHS = new Set(rawPaths.split("|").filter(Boolean));
