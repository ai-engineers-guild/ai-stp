/** Argument kinds are independent of wording and locale-specific plural cases. */
export function parameters(nodes, result = new Map()) {
  for (const node of nodes) {
    if (node.type >= 1 && node.type <= 6) {
      const type =
        node.type === 2 || node.type === 6
          ? "number"
          : node.type === 3 || node.type === 4
            ? "Date | number"
            : node.type === 5
              ? "string"
              : "string | number";
      const previous = result.get(node.value);
      if (
        previous &&
        previous !== type &&
        previous !== "string | number" &&
        type !== "string | number"
      )
        throw new Error(
          `Conflicting message argument kinds for ${node.value}: ${previous}, ${type}`,
        );
      if (!previous || previous === "string | number")
        result.set(node.value, type);
    }
    if (node.children) parameters(node.children, result);
    if (node.options)
      for (const option of Object.values(node.options))
        parameters(option.value, result);
  }
  return result;
}

/** Selector tokens are protocol values, unlike locale-specific plural cases. */
export function selectors(nodes, result = new Map()) {
  for (const node of nodes) {
    if (node.type === 5) {
      const choices = result.get(node.value) ?? new Set();
      for (const choice of Object.keys(node.options)) choices.add(choice);
      result.set(node.value, choices);
    }
    if (node.children) selectors(node.children, result);
    if (node.options)
      for (const option of Object.values(node.options))
        selectors(option.value, result);
  }
  return JSON.stringify(
    [...result]
      .map(([name, choices]) => [
        name,
        [...choices].sort((left, right) =>
          left < right ? -1 : left > right ? 1 : 0,
        ),
      ])
      .sort(([a], [b]) => a.localeCompare(b)),
  );
}
