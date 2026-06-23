"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupInput, InputGroupText } from "@/components/ui/input-group";
import { Spinner } from "@/components/ui/spinner";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  createOptionGroupDraft,
  createOptionGroupDraftFromLibrary,
  createOptionItemDraft,
  type MenuOptionGroupDraft,
  type ModifierGroupOut,
} from "@/lib/menu";
import { cn } from "@/lib/utils";

type ModifierTemplateDialogProps = {
  open: boolean;
  groups: ModifierGroupOut[];
  isSaving: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (group: MenuOptionGroupDraft) => void;
  onDelete: (group: ModifierGroupOut) => void;
};

function newTemplateDraft(): MenuOptionGroupDraft {
  return createOptionGroupDraft({ isTemplate: true });
}

function TemplateForm({
  initialGroup,
  isSaving,
  onSave,
  onDelete,
}: {
  initialGroup: MenuOptionGroupDraft;
  isSaving: boolean;
  onSave: (group: MenuOptionGroupDraft) => void;
  onDelete?: () => void;
}) {
  const [draft, setDraft] = useState(initialGroup);
  const isValid =
    Boolean(draft.name.trim()) &&
    Boolean(draft.displayName.trim()) &&
    draft.items.length > 0 &&
    draft.items.every((item) => item.name.trim());

  function patch(patch: Partial<MenuOptionGroupDraft>) {
    setDraft((current) => ({ ...current, ...patch }));
  }

  function patchItem(clientId: string, patch: Partial<MenuOptionGroupDraft["items"][number]>) {
    setDraft((current) => ({
      ...current,
      items: current.items.map((item) =>
        item.clientId === clientId ? { ...item, ...patch } : item,
      ),
    }));
  }

  return (
    <form
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        if (isValid) onSave(draft);
      }}
    >
      <div className="min-h-0 flex-1 overflow-y-auto px-1 pb-1">
        <FieldGroup className="gap-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field>
              <FieldLabel htmlFor="template-internal-name">Internal name</FieldLabel>
              <Input
                id="template-internal-name"
                value={draft.name}
                onChange={(event) => patch({ name: event.target.value })}
                placeholder="Pizza sizes"
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="template-display-name">Customer label</FieldLabel>
              <Input
                id="template-display-name"
                value={draft.displayName}
                onChange={(event) => patch({ displayName: event.target.value })}
                placeholder="Size"
              />
            </Field>
          </div>

          <Field>
            <FieldLabel>Selection type</FieldLabel>
            <ToggleGroup
              value={[draft.selectType]}
              onValueChange={(value) => {
                if (value[0]) patch({ selectType: value[0] as "single" | "multi" });
              }}
              variant="outline"
              spacing={2}
              aria-label="Template selection type"
            >
              <ToggleGroupItem value="single">Single choice</ToggleGroupItem>
              <ToggleGroupItem value="multi">Multiple choice</ToggleGroupItem>
            </ToggleGroup>
          </Field>

          <Field>
            <div className="flex items-center justify-between gap-3">
              <FieldLabel>Options</FieldLabel>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => patch({ items: [...draft.items, createOptionItemDraft()] })}
              >
                <Plus data-icon="inline-start" />
                Add option
              </Button>
            </div>
            <div className="mt-2 flex flex-col gap-2">
              {draft.items.map((item) => (
                <div
                  key={item.clientId}
                  className="grid grid-cols-[minmax(0,1fr)_112px_64px_32px] items-center gap-2"
                >
                  <div className="flex min-w-0 flex-col gap-2">
                    <Input
                      value={item.name}
                      onChange={(event) => patchItem(item.clientId, { name: event.target.value })}
                      aria-label="Template option name"
                      placeholder="Option name"
                    />
                    <Textarea
                      value={item.description}
                      onChange={(event) =>
                        patchItem(item.clientId, { description: event.target.value })
                      }
                      aria-label={`${item.name || "Option"} customer details`}
                      placeholder="Customer details, e.g. 13-inch diameter, serves 1-2"
                      rows={1}
                      maxLength={500}
                      className="min-h-9 resize-y py-1.5"
                    />
                  </div>
                  <InputGroup>
                    <InputGroupAddon>
                      <InputGroupText>+ R</InputGroupText>
                    </InputGroupAddon>
                    <InputGroupInput
                      type="number"
                      min="0"
                      step="0.01"
                      value={item.priceDelta}
                      onChange={(event) =>
                        patchItem(item.clientId, { priceDelta: event.target.value })
                      }
                      aria-label={`${item.name || "Option"} suggested price`}
                    />
                  </InputGroup>
                  <div className="flex justify-center">
                    <Switch
                      size="sm"
                      checked={item.isDefault}
                      onCheckedChange={(checked) => {
                        setDraft((current) => ({
                          ...current,
                          items: current.items.map((candidate) => ({
                            ...candidate,
                            isDefault:
                              candidate.clientId === item.clientId
                                ? checked
                                : current.selectType === "single"
                                  ? false
                                  : candidate.isDefault,
                          })),
                        }));
                      }}
                      aria-label={`${item.name || "Option"} suggested default`}
                    />
                  </div>
                  <Button
                    type="button"
                    variant="destructive"
                    size="icon-sm"
                    onClick={() =>
                      patch({ items: draft.items.filter((candidate) => candidate.clientId !== item.clientId) })
                    }
                    disabled={draft.items.length === 1}
                    aria-label={`Delete ${item.name || "option"}`}
                  >
                    <Trash2 />
                  </Button>
                </div>
              ))}
            </div>
          </Field>
        </FieldGroup>
      </div>

      <DialogFooter className="mt-4 -mx-0 -mb-0 rounded-none bg-transparent p-0 pt-4">
        {onDelete ? (
          <Button
            type="button"
            variant="destructive"
            onClick={onDelete}
            disabled={isSaving}
            className="sm:mr-auto"
          >
            <Trash2 data-icon="inline-start" />
            Delete template
          </Button>
        ) : null}
        <Button type="submit" disabled={isSaving || !isValid}>
          {isSaving ? <Spinner data-icon="inline-start" /> : null}
          {draft.modifierGroupId ? "Save template" : "Create template"}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function ModifierTemplateManagerContent({
  groups,
  isSaving,
  onSave,
  onDelete,
}: Omit<ModifierTemplateDialogProps, "open" | "onOpenChange">) {
  const [selectedId, setSelectedId] = useState<string | null>(groups[0]?.id ?? null);
  const selected = groups.find((group) => group.id === selectedId);
  const initialDraft = selected
    ? createOptionGroupDraftFromLibrary(selected)
    : newTemplateDraft();

  return (
    <div className="contents">
      <div className="flex flex-col gap-2">
        <h2 className="font-heading text-base leading-none font-medium">
          Modifier templates
        </h2>
        <p className="text-sm text-muted-foreground">
          Reuse option definitions across dishes and customize availability and prices per dish.
        </p>
      </div>

      <div className="grid min-h-0 flex-1 gap-4 border-t border-border pt-4 md:grid-cols-[180px_minmax(0,1fr)]">
          <aside className="flex min-h-0 flex-col border-b border-border pb-4 md:border-r md:border-b-0 md:pr-4 md:pb-0">
            <Button
              type="button"
              variant="outline"
              onClick={() => setSelectedId(null)}
            >
              <Plus data-icon="inline-start" />
              Create template
            </Button>
            <div className="mt-3 flex min-h-0 flex-col gap-1 overflow-y-auto">
              {groups.length === 0 ? (
                <p className="py-6 text-center text-sm text-muted-foreground">
                  No templates yet
                </p>
              ) : (
                groups.map((group) => (
                  <button
                    key={group.id}
                    type="button"
                    onClick={() => setSelectedId(group.id)}
                    className={cn(
                      "rounded-md px-2.5 py-2 text-left text-sm transition-colors",
                      selectedId === group.id
                        ? "bg-muted font-medium text-foreground"
                        : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                    )}
                  >
                    <span className="block truncate">{group.name}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {group.display_name}
                    </span>
                  </button>
                ))
              )}
            </div>
          </aside>

          <TemplateForm
            key={selected?.id ?? "new"}
            initialGroup={initialDraft}
            isSaving={isSaving}
            onSave={onSave}
            onDelete={selected ? () => onDelete(selected) : undefined}
          />
      </div>
    </div>
  );
}

export function ModifierTemplateDialog({
  open,
  groups,
  isSaving,
  onOpenChange,
  onSave,
  onDelete,
}: ModifierTemplateDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[min(720px,calc(100svh-2rem))] min-h-0 flex-col overflow-hidden sm:max-w-[760px]">
        <DialogTitle className="sr-only">Modifier templates</DialogTitle>
        <DialogDescription className="sr-only">
          Create and edit reusable modifier templates.
        </DialogDescription>
        <ModifierTemplateManagerContent
          groups={groups}
          isSaving={isSaving}
          onSave={onSave}
          onDelete={onDelete}
        />
      </DialogContent>
    </Dialog>
  );
}
