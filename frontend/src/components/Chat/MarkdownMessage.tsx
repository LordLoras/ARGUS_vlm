import type { ReactNode } from "react";

export function MarkdownMessage({ content }: { content: string }) {
  return <div className="md-message">{renderBlocks(content)}</div>;
}

function renderBlocks(content: string): ReactNode[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];
  let list: string[] = [];
  let orderedList: string[] = [];
  let code: string[] | null = null;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const text = paragraph.join(" ").trim();
    if (text) blocks.push(<p key={`p-${blocks.length}`}>{renderInline(text)}</p>);
    paragraph = [];
  };

  const flushList = () => {
    if (list.length) {
      blocks.push(
        <ul key={`ul-${blocks.length}`}>
          {list.map((item, index) => (
            <li key={index}>{renderInline(item)}</li>
          ))}
        </ul>
      );
      list = [];
    }
    if (orderedList.length) {
      blocks.push(
        <ol key={`ol-${blocks.length}`}>
          {orderedList.map((item, index) => (
            <li key={index}>{renderInline(item)}</li>
          ))}
        </ol>
      );
      orderedList = [];
    }
  };

  const flushText = () => {
    flushParagraph();
    flushList();
  };

  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      if (code === null) {
        flushText();
        code = [];
      } else {
        blocks.push(<pre key={`pre-${blocks.length}`}>{code.join("\n")}</pre>);
        code = null;
      }
      continue;
    }

    if (code !== null) {
      code.push(line);
      continue;
    }

    if (!line.trim()) {
      flushText();
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      flushText();
      const Tag = heading[1].length === 1 ? "h3" : "h4";
      blocks.push(<Tag key={`h-${blocks.length}`}>{renderInline(heading[2])}</Tag>);
      continue;
    }

    const bullet = /^\s*[-*]\s+(.+)$/.exec(line);
    if (bullet) {
      flushParagraph();
      orderedList = [];
      list.push(bullet[1]);
      continue;
    }

    const numbered = /^\s*\d+\.\s+(.+)$/.exec(line);
    if (numbered) {
      flushParagraph();
      list = [];
      orderedList.push(numbered[1]);
      continue;
    }

    flushList();
    paragraph.push(line.trim());
  }

  if (code !== null) {
    blocks.push(<pre key={`pre-${blocks.length}`}>{code.join("\n")}</pre>);
  }
  flushText();

  return blocks.length ? blocks : [content];
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\((https?:\/\/[^)]+)\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text))) {
    if (match.index > lastIndex) nodes.push(text.slice(lastIndex, match.index));
    const token = match[0];
    if (token.startsWith("**")) {
      nodes.push(<strong key={nodes.length}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      nodes.push(<code key={nodes.length}>{token.slice(1, -1)}</code>);
    } else {
      nodes.push(
        <a key={nodes.length} href={match[2]} target="_blank" rel="noreferrer">
          {token.slice(1, token.indexOf("]"))}
        </a>
      );
    }
    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < text.length) nodes.push(text.slice(lastIndex));
  return nodes;
}
