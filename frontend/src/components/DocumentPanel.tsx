import type { DocumentView } from "../types";

// Rendered as React text nodes (never innerHTML), so user-supplied text cannot inject markup.
export default function DocumentPanel({ doc }: { doc: DocumentView }) {
  return (
    <section className="panel docwrap" aria-label="Document preview">
      <h2>Document preview</h2>
      <article className={`paper ${doc.status}`}>
        <div className="stamp">{doc.disclaimer}</div>
        <h3>{doc.title}</h3>
        <p className="docstatus">{doc.status === "complete" ? "Complete draft" : "Incomplete draft — some details are still missing"}</p>
        {doc.sections.map((s) => (
          <section key={s.heading}>
            <h4>{s.heading}</h4>
            {s.lines.map((line, i) => (
              <p key={i} className={line.startsWith("[") ? "placeholder" : undefined}>
                {line}
              </p>
            ))}
          </section>
        ))}
        <footer>{doc.disclaimer}. For demonstration only.</footer>
      </article>
    </section>
  );
}
