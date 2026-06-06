import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  breaks: false,
})

function normalizeMarkdown(source: string): string {
  const lines = source.split('\n')
  const out: string[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    // Merge empty list markers with the next non-empty line
    const numMatch = line.match(/^(\d+)\.\s*$/)
    const bulletMatch = line.match(/^-\s*$/)
    if (numMatch || bulletMatch) {
      let j = i + 1
      while (j < lines.length && lines[j].trim() === '') j++
      if (j < lines.length) {
        const prefix = numMatch ? numMatch[1] + '. ' : '- '
        out.push(prefix + lines[j])
        i = j + 1
        continue
      }
    }
    out.push(line)
    i++
  }
  return out.join('\n')
}

export function useMarkdown() {
  function render(source: string): string {
    if (!source) return ''
    return md.render(normalizeMarkdown(source))
  }

  return { render }
}
