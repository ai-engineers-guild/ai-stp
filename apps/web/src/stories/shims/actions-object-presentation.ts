/** Storybook no-op for object presentation server actions. */
export async function updateObjectPresentationAction(_input: unknown): Promise<never> {
  throw new Error("presentation write unavailable in Storybook");
}

export async function deleteObjectAction(_input: unknown): Promise<never> {
  throw new Error("object delete unavailable in Storybook");
}
