import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const copy: Record<string, { title: string; body: string }> = {
  upload: {
    title: 'Upload Center',
    body: 'Media uploads are disabled in this catalog administration milestone. Encoding and CDN pipelines will be wired in a later phase.',
  },
  encoding: {
    title: 'Encoding Queue',
    body: 'Encoding job management is not enabled yet. Catalog publish/unpublish does not trigger encoding.',
  },
  cdn: {
    title: 'CDN Management',
    body: 'CDN node management and sync are disabled for this milestone.',
  },
  users: {
    title: 'Users',
    body: 'Subscriber and Radius administration remain out of scope. Use catalog sections to manage content.',
  },
};

export default function AdminPlaceholderPage({ section }: { section: keyof typeof copy }) {
  const item = copy[section] || copy.upload;
  return (
    <Card className="bg-card border-border max-w-2xl">
      <CardHeader>
        <CardTitle className="text-base">{item.title}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground space-y-2">
        <p>{item.body}</p>
        <p>This page is a placeholder so existing admin navigation remains available.</p>
      </CardContent>
    </Card>
  );
}
