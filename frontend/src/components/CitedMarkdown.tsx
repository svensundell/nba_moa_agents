import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

const CITE_RE = /\[(\d{1,3})\]/g;

function injectCitationLinks(
  text: string,
  onCitationClick?: (id: number) => void,
): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  const re = new RegExp(CITE_RE.source, "g");
  while ((match = re.exec(text)) !== null) {
    const id = Number(match[1]);
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }
    parts.push(
      <button
        key={`cite-${match.index}-${id}`}
        type="button"
        className="align-super text-[0.7em] font-semibold text-accent hover:underline mx-0.5"
        onClick={() => {
          onCitationClick?.(id);
          const el = document.getElementById(`source-${id}`);
          el?.scrollIntoView({ behavior: "smooth", block: "center" });
        }}
        title={`Source [${id}]`}
      >
        [{id}]
      </button>,
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    parts.push(text.slice(last));
  }
  return parts.length > 0 ? parts : [text];
}

function CitedText({
  children,
  onCitationClick,
}: {
  children?: React.ReactNode;
  onCitationClick?: (id: number) => void;
}) {
  if (!onCitationClick) return <>{children}</>;
  if (typeof children === "string") {
    return <>{injectCitationLinks(children, onCitationClick)}</>;
  }
  if (Array.isArray(children)) {
    return (
      <>
        {children.map((child, i) =>
          typeof child === "string" ? (
            <span key={i}>{injectCitationLinks(child, onCitationClick)}</span>
          ) : (
            <span key={i}>{child}</span>
          ),
        )}
      </>
    );
  }
  return <>{children}</>;
}

export function CitedMarkdown({
  content,
  onCitationClick,
}: {
  content: string;
  onCitationClick?: (id: number) => void;
}) {
  const components: Components = {
    p: ({ children }) => (
      <p>
        <CitedText onCitationClick={onCitationClick}>{children}</CitedText>
      </p>
    ),
    li: ({ children }) => (
      <li>
        <CitedText onCitationClick={onCitationClick}>{children}</CitedText>
      </li>
    ),
  };

  return (
    <div className="prose-brief">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
