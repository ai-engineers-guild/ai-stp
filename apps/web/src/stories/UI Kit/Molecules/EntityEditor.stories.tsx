import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";

import { Button } from "@/components/atoms/button";
import { Input } from "@/components/atoms/input";
import {
  EntityEditorField,
  EntityEditorLayout,
  EntityEditorSection,
} from "@/components/molecules/entity-editor-layout";
import { EntityLinksEditor } from "@/components/molecules/entity-links-editor";
import { MarkdownEditor } from "@/components/molecules/markdown-editor";
import { ENTITY_EDITOR_CONFIGS, type EntityEditorLink } from "@/lib/entity-editor-contract";

function EditorFixture({ preview = false }: { preview?: boolean }) {
  const [mode, setMode] = useState<"write" | "preview">(preview ? "preview" : "write");
  const [description, setDescription] = useState(
    "# Growth Experiments\n\n**Public** product work.",
  );
  const [links, setLinks] = useState<EntityEditorLink[]>([
    { label: "Website", url: "https://growth.ai-stp.dev" },
  ]);

  return (
    <div className="mx-auto max-w-3xl p-6">
      <EntityEditorLayout
        config={ENTITY_EDITOR_CONFIGS.project}
        title="Edit public presentation"
        description="Shared editor geometry for projects, teams, and technologies."
      >
        <EntityEditorSection title="Identity">
          <EntityEditorField label="Display name" htmlFor="story-name" required>
            <Input id="story-name" defaultValue="Growth Experiments" />
          </EntityEditorField>
        </EntityEditorSection>
        <MarkdownEditor
          id="story-description"
          label="Description"
          value={description}
          mode={mode}
          onChange={setDescription}
          onModeChange={setMode}
          maxLength={20_000}
          labels={{ write: "Write", preview: "Preview" }}
        />
        <EntityLinksEditor
          links={links}
          max={5}
          onChange={setLinks}
          labels={{
            title: "Links",
            add: "Add",
            empty: "No links yet.",
            label: "Label",
            url: "URL (HTTPS)",
            remove: "Remove",
          }}
        />
        <div className="flex justify-end border-t pt-4">
          <Button>Save</Button>
        </div>
      </EntityEditorLayout>
    </div>
  );
}

const meta = {
  title: "UI Kit/Molecules/EntityEditor",
  component: EntityEditorLayout,
  tags: ["autodocs"],
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof EntityEditorLayout>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => <EditorFixture />,
};

export const MarkdownPreview: Story = {
  render: () => <EditorFixture preview />,
};
