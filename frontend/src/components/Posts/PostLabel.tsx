import type { TopPost } from "@/client"
import { PlatformIcon } from "@/components/Integrations/PlatformIcon"
import { Badge } from "@/components/ui/badge"

/**
 * The post's content type and the start of its text, linking to the post;
 * `showPlatform` adds its platform's icon, for lists that mix platforms.
 */
export function PostLabel({
  post,
  showPlatform = false,
}: {
  post: Pick<
    TopPost,
    "text" | "external_id" | "platform" | "content_type" | "permalink"
  >
  showPlatform?: boolean
}) {
  const text = post.text?.slice(0, 80) ?? post.external_id
  return (
    <div className="flex items-center gap-2">
      {showPlatform && (
        <PlatformIcon platform={post.platform} className="size-5 shrink-0" />
      )}
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
