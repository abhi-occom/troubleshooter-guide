import { ChevronDown, FileText } from "lucide-react";
import type { Citation } from "../types";

export function Citations({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;

  return (
    <div className="citations">
      <p>Sources</p>
      {citations.map((citation, index) => (
        <details key={`${citation.document_id}-${citation.page}-${index}`}>
          <summary>
            <FileText size={14} />
            <span>{citation.document}</span>
            <b>Page {citation.page}</b>
            <ChevronDown size={14} />
          </summary>
          <blockquote>{citation.excerpt}</blockquote>
        </details>
      ))}
    </div>
  );
}

