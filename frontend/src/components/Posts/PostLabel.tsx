import type { PostPublic } from "@/client"
import { Badge } from "@/components/ui/badge"

/** The post's content type and the start of its text, linking to the post. */
export function PostLabel({ post }: { post: PostPublic }) {
  const text = post.text?.slice(0, 80) ?? post.external_id
  return (
    <div className="flex items-center gap-2">
      <Badge variant="secondary" className="shrink-0 text-xs capitalize">
        {post.content_type}
      </Badge>
      {post.permalink ? (
        <a
          href={post.permalink}
          target="_blank"
          rel="noopener noreferrer"
          className="block truncate text-sm hover:underline"
        >
          {text}
        </a>
      ) : (
        <span className="block truncate text-sm text-muted-foreground">
          {text}
        </span>
      )}
    </div>
  )
}
