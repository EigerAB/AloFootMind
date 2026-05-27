import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  breaks: true,
})

export function useMarkdown() {
  function render(source: string): string {
    if (!source) return ''
    return md.render(source)
  }

  return { render }
}
