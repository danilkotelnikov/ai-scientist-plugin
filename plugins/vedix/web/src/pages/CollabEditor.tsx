/**
 * §5.11 — Collaborative manuscript editor.
 *
 * Mounts a <YjsProvider> for the doc id taken from the URL
 * (``/collab/:docId``), binds a textarea to ``doc.getText("manuscript")``
 * and overlays presence cursors. The textarea is intentionally
 * unstyled — Block 12 (polish) will swap it for a richer editor.
 */
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import * as Y from "yjs";
import { CursorOverlay } from "../collab/CursorOverlay";
import { YjsProvider, useYjs } from "../collab/YjsProvider";

interface EditorProps {
  myName: string;
}

function Editor({ myName }: EditorProps): JSX.Element {
  const { doc, status } = useYjs();
  const ref = useRef<HTMLTextAreaElement>(null);
  const [text, setText] = useState<string>("");

  // Bind the textarea to a Y.Text-rooted shared string.
  useEffect(() => {
    const ytext = doc.getText("manuscript");
    setText(ytext.toString());
    const onYChange = (): void => {
      const next = ytext.toString();
      setText(next);
      if (ref.current && ref.current.value !== next) {
        ref.current.value = next;
      }
    };
    ytext.observe(onYChange);

    const el = ref.current;
    if (!el) {
      return () => {
        ytext.unobserve(onYChange);
      };
    }
    el.value = ytext.toString();
    const onInput = (): void => {
      const local = el.value;
      // Replace-all is the simplest CRDT-safe binding for a plain
      // textarea; richer editors can use the per-keystroke diff path.
      Y.transact(doc, () => {
        ytext.delete(0, ytext.length);
        ytext.insert(0, local);
      });
    };
    el.addEventListener("input", onInput);
    return () => {
      ytext.unobserve(onYChange);
      el.removeEventListener("input", onInput);
    };
  }, [doc]);

  return (
    <>
      <div className="text-xs text-gray-500 px-4 py-1 border-b">
        Collaboration:&nbsp;<span data-testid="collab-status">{status}</span>
        &nbsp;·&nbsp;
        <span data-testid="collab-doc-size">{text.length}</span> chars
      </div>
      <textarea
        ref={ref}
        data-testid="collab-textarea"
        className="w-full h-screen p-6 font-mono outline-none border-0"
        placeholder="Start typing — every keystroke is synchronised over Yjs."
      />
      <CursorOverlay myName={myName} />
    </>
  );
}

export function CollabEditor(): JSX.Element {
  const { docId } = useParams<{ docId: string }>();
  if (!docId) {
    return (
      <div className="p-12 text-center text-gray-500">
        Missing document id in URL — open /collab/&lt;docId&gt; instead.
      </div>
    );
  }
  // For now we use a placeholder display name. Block 12 will populate
  // this from the authenticated user profile.
  return (
    <YjsProvider docId={docId}>
      <Editor myName="You" />
    </YjsProvider>
  );
}
