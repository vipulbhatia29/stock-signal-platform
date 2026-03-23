"use client";

import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";

// Hoisted to module level to avoid plugin pipeline reinit on every render/token flush
const REMARK_PLUGINS = [remarkGfm];
const REHYPE_PLUGINS = [rehypeHighlight];

interface MarkdownContentProps {
  content: string;
  isStreaming?: boolean;
}

export function MarkdownContent({ content, isStreaming }: MarkdownContentProps) {
  return (
    <div className="prose prose-sm prose-invert max-w-none break-words [&_pre]:bg-card [&_pre]:rounded-md [&_pre]:p-3 [&_pre]:text-xs [&_code]:bg-card [&_code]:rounded [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_a]:text-accent [&_a]:underline [&_table]:text-xs [&_th]:border [&_th]:border-border [&_th]:px-2 [&_th]:py-1 [&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1">
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={REHYPE_PLUGINS}
      >
        {content}
      </ReactMarkdown>
      {isStreaming && (
        <span className="inline-block h-4 w-1.5 animate-pulse bg-accent ml-0.5 align-text-bottom" />
      )}
    </div>
  );
}
