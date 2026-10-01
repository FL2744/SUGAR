import { useEffect, useMemo, useRef, useState } from "react";

export type Command = { id: string; label: string; hint?: string; keywords?: string; run: () => void };

/** Ctrl/⌘+K: jump anywhere or run an action by typing a few letters. */
export function CommandPalette({ commands, onClose }: { commands: Command[]; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const opener = useRef<Element | null>(document.activeElement);

  const matches = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return commands;
    return commands.filter((c) => { const hay = `${c.label} ${c.keywords || ""}`.toLowerCase(); return words.every((w) => hay.includes(w)); });
  }, [commands, query]);

  useEffect(() => { input.current?.focus(); const previous = opener.current as HTMLElement | null; return () => previous?.focus?.(); }, []);
  useEffect(() => { setIndex(0); }, [query]);

  const choose = (command: Command | undefined) => { if (!command) return; onClose(); window.setTimeout(command.run, 0); };
  const onKey = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") { event.preventDefault(); setIndex((i) => Math.min(matches.length - 1, i + 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setIndex((i) => Math.max(0, i - 1)); }
    else if (event.key === "Enter") { event.preventDefault(); choose(matches[index]); }
    else if (event.key === "Escape") { event.preventDefault(); onClose(); }
  };

  return (
    <div className="modal-backdrop palette-backdrop" onClick={onClose}>
      <section className="modal palette" role="dialog" aria-modal="true" aria-label="Command palette" onClick={(event) => event.stopPropagation()} onKeyDown={onKey}>
        <input ref={input} className="palette-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Type a command or page…" role="combobox"
          aria-expanded="true" aria-controls="palette-list" aria-activedescendant={matches[index] ? `cmd-${matches[index].id}` : undefined} aria-label="Search commands" />
        <ul id="palette-list" role="listbox" aria-label="Commands">
          {matches.map((c, i) => (
            <li key={c.id} id={`cmd-${c.id}`} role="option" aria-selected={i === index} className={i === index ? "on" : ""} onMouseEnter={() => setIndex(i)} onClick={() => choose(c)}>
              <span>{c.label}</span>{c.hint && <kbd>{c.hint}</kbd>}
            </li>))}
          {matches.length === 0 && <li className="muted palette-empty">Nothing matches “{query}”.</li>}
        </ul>
        <footer className="palette-foot"><span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>Enter</kbd> run</span><span><kbd>Esc</kbd> close</span></footer>
      </section>
    </div>
  );
}

const SHORTCUTS: Array<[string, string]> = [
  ["Ctrl / ⌘ + K", "Open the command palette"], ["?", "Show this help"], ["Ctrl / ⌘ + Enter", "Interpret the request (Research page)"],
  ["Esc", "Close a panel or dialog"],
];

export function ShortcutHelp({ onClose }: { onClose: () => void }) {
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => { close.current?.focus(); }, []);
  return (
    <div className="modal-backdrop" onClick={onClose} onKeyDown={(event) => { if (event.key === "Escape") onClose(); }}>
      <section className="modal shortcut-help" role="dialog" aria-modal="true" aria-labelledby="shortcuts-title" onClick={(event) => event.stopPropagation()}>
        <header className="modal-head"><h2 id="shortcuts-title">Keyboard shortcuts</h2><button ref={close} className="text-button" onClick={onClose}>Close</button></header>
        <div className="modal-body"><dl className="kv">{SHORTCUTS.map(([keys, what]) => <div key={keys}><dt><kbd>{keys}</kbd></dt><dd>{what}</dd></div>)}</dl></div>
      </section>
    </div>
  );
}
