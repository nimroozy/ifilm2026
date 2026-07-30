import { useEffect, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { adminApi, ApiError, tokenStore } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Alert, AlertDescription } from '@/components/ui/alert';

const schema = z.object({
  username: z.string().min(1, 'Username is required'),
  password: z.string().min(1, 'Password is required'),
});

type FormValues = z.infer<typeof schema>;

export default function AdminLoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { username: '', password: '' },
  });

  useEffect(() => {
    let cancelled = false;
    async function checkExisting() {
      if (!tokenStore.getAdmin()) {
        if (!cancelled) setChecking(false);
        return;
      }
      try {
        await adminApi.me();
        if (!cancelled) navigate('/admin', { replace: true });
      } catch {
        tokenStore.clearAdmin();
        if (!cancelled) setChecking(false);
      }
    }
    checkExisting();
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  async function onSubmit(values: FormValues) {
    setError(null);
    try {
      // Do not log credentials
      await adminApi.login(values.username, values.password);
      const from = (location.state as { from?: string } | null)?.from || '/admin';
      navigate(from, { replace: true });
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : 'Login failed. Check your credentials.';
      setError(message);
    }
  }

  if (checking) {
    return <div className="min-h-screen bg-background" />;
  }

  if (tokenStore.getAdmin() && !error && form.formState.isSubmitSuccessful) {
    return <Navigate to="/admin" replace />;
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-md bg-card border-border">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl font-serif text-primary">Mobin Play</CardTitle>
          <CardDescription>Admin Panel Sign In</CardDescription>
        </CardHeader>
        <CardContent>
          {error && (
            <Alert variant="destructive" className="mb-4" data-testid="login-error">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
              <FormField
                control={form.control}
                name="username"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Username</FormLabel>
                    <FormControl>
                      <Input autoComplete="username" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Password</FormLabel>
                    <FormControl>
                      <Input type="password" autoComplete="current-password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button
                type="submit"
                className="w-full bg-primary text-primary-foreground"
                disabled={form.formState.isSubmitting}
              >
                {form.formState.isSubmitting ? 'Signing in…' : 'Sign In'}
              </Button>
            </form>
          </Form>
          <p className="text-xs text-muted-foreground mt-4 text-center">
            <Link to="/" className="hover:text-foreground underline-offset-2 hover:underline">
              ← Back to app
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
