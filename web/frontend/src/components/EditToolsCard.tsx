import { createEffect, createSignal, Show } from 'solid-js';
import type { ResolveResult } from '../api';
import { validateFolder } from '../api';
import { CutIcon, FolderIcon, RenameIcon } from './IconButton';
import TimeField, { durationHint } from './TimeField';
import { formatDurationSec } from '../lib/time';

export type ToolId = 'cut' | 'rename' | 'save';

type Props = {
  meta: ResolveResult;
  durationSec: number | null;
  cutStart: string;
  cutEnd: string;
  startFieldError: string;
  endFieldError: string;
  endPlaceholder: string;
  customTitle: string;
  savePath: string;
  rememberSavePath: boolean;
  activeTool: ToolId | null;
  onCutStartChange: (value: string) => void;
  onCutEndChange: (value: string) => void;
  onNormalizeStart: (value: string) => void;
  onNormalizeEnd: (value: string) => void;
  onCustomTitleChange: (value: string) => void;
  onSavePathChange: (value: string) => void;
  onRememberSavePathChange: (value: boolean) => void;
  onSelectTool: (tool: ToolId) => void;
};

const TOOLS: Array<{
  id: ToolId;
  label: string;
  hint: string;
  Icon: typeof CutIcon;
}> = [
  { id: 'cut', label: 'Cut', hint: 'Trim start and end timestamps', Icon: CutIcon },
  { id: 'rename', label: 'Rename title', hint: 'Custom output filename title', Icon: RenameIcon },
  { id: 'save', label: 'Save location', hint: 'Choose download folder path', Icon: FolderIcon },
];

export default function EditToolsCard(props: Props) {
  const [pathError, setPathError] = createSignal('');
  const [draftPath, setDraftPath] = createSignal(props.savePath);

  createEffect(() => {
    setDraftPath(props.savePath);
  });

  async function applyPath() {
    const path = draftPath().trim();
    if (!path) return;

    setPathError('');
    const result = await validateFolder(path);
    if (!result.ok || !result.path) {
      setPathError(result.error || 'Folder is not writable or does not exist');
      return;
    }
    setDraftPath(result.path);
    props.onSavePathChange(result.path);
    if (props.rememberSavePath) {
      props.onRememberSavePathChange(true);
    }
  }

  const activeMeta = () => TOOLS.find((tool) => tool.id === props.activeTool);

  return (
    <section class="card edit-tools">
      <p class="edit-tools-heading">Video tools</p>
      <div class="edit-tools-layout">
        <nav class="edit-tools-sidebar" aria-label="Video tools">
          {TOOLS.map((tool) => (
            <button
              type="button"
              class={`tool-sidebar-btn ${props.activeTool === tool.id ? 'active' : ''}`}
              aria-pressed={props.activeTool === tool.id}
              onClick={() => props.onSelectTool(tool.id)}
            >
              <tool.Icon />
              <span>{tool.label}</span>
            </button>
          ))}
        </nav>

        <div class="edit-tools-panel">
          <Show
            when={props.activeTool}
            fallback={
              <div class="tool-panel-empty">
                <p class="tool-panel-title">Select a tool</p>
                <p class="hint">Pick a tool from the left sidebar to edit download options.</p>
              </div>
            }
          >
            {(toolId) => (
              <>
                <p class="tool-panel-title">{activeMeta()?.label}</p>
                <p class="tool-panel-desc">{activeMeta()?.hint}</p>

                <Show when={toolId() === 'cut'}>
                  <div class="cut-row">
                    <TimeField
                      id="cut-start"
                      label="Start at"
                      value={props.cutStart}
                      placeholder="0:00"
                      hint={durationHint(props.durationSec ?? undefined)}
                      error={props.startFieldError}
                      onChange={props.onCutStartChange}
                      onBlurNormalize={props.onNormalizeStart}
                    />
                    <TimeField
                      id="cut-end"
                      label="End at"
                      value={props.cutEnd}
                      placeholder={props.endPlaceholder}
                      hint={
                        props.durationSec
                          ? `Max ${formatDurationSec(props.durationSec)} · leave empty for full`
                          : 'Leave empty for full video'
                      }
                      error={props.endFieldError}
                      onChange={props.onCutEndChange}
                      onBlurNormalize={props.onNormalizeEnd}
                    />
                  </div>
                  <p class="hint">
                    Use <code>mm:ss</code> or seconds (e.g. <code>90</code> → <code>1:30</code>).
                  </p>
                </Show>

                <Show when={toolId() === 'rename'}>
                  <label for="output-title">Output title</label>
                  <textarea
                    id="output-title"
                    class="title-textarea mono"
                    rows={4}
                    autocomplete="off"
                    spellcheck={false}
                    placeholder={props.meta.title || 'Video title'}
                    value={props.customTitle}
                    onInput={(event) => props.onCustomTitleChange(event.currentTarget.value)}
                  />
                </Show>

                <Show when={toolId() === 'save'}>
                  <label for="save-path">Save folder</label>
                  <div class="save-path-field">
                    <FolderIcon />
                    <input
                      id="save-path"
                      type="text"
                      class="mono save-path-input"
                      autocomplete="off"
                      spellcheck={false}
                      placeholder="/home/you/Documents/jav"
                      value={draftPath()}
                      onInput={(event) => {
                        setDraftPath(event.currentTarget.value);
                        setPathError('');
                      }}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                          event.preventDefault();
                          void applyPath();
                        }
                      }}
                    />
                  </div>
                  <label class="remember-path">
                    <input
                      type="checkbox"
                      checked={props.rememberSavePath}
                      onChange={(event) =>
                        props.onRememberSavePathChange(event.currentTarget.checked)
                      }
                    />
                    <span>Remember this folder for future downloads</span>
                  </label>
                  <div class="save-path-actions">
                    <button
                      type="button"
                      class="tool-btn subtle"
                      disabled={!draftPath().trim()}
                      onClick={() => void applyPath()}
                    >
                      Apply
                    </button>
                  </div>
                  <Show when={pathError()}>
                    <p class="time-error">{pathError()}</p>
                  </Show>
                </Show>
              </>
            )}
          </Show>
        </div>
      </div>
    </section>
  );
}
