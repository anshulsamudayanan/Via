import { Button, EmptyState } from "@via/ui";
import { FileQuestion } from "lucide-react";
import Link from "next/link";

export default function NotFound() {
  return (
    <EmptyState
      icon={<FileQuestion />}
      title="Page not found"
      description="The page you're looking for doesn't exist or has moved."
      action={
        <Button asChild size="sm">
          <Link href="/">Back to home</Link>
        </Button>
      }
    />
  );
}
