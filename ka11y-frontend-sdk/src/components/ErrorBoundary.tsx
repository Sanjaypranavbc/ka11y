import { Component, ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surface to an external error tracking service if available
    const w = window as Window & { Sentry?: { captureException: (e: Error, ctx: object) => void } };
    w.Sentry?.captureException(error, { extra: info });
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div role="alert" className="flex min-h-screen items-center justify-center bg-muted">
          <div className="max-w-md rounded-lg border bg-background p-8 text-center shadow">
            <h1 className="mb-2 text-2xl font-bold">Something went wrong</h1>
            <p className="mb-4 text-muted-foreground">
              An unexpected error occurred. Please refresh the page and try again.
            </p>
            <details className="text-left text-sm text-muted-foreground">
              <summary className="cursor-pointer select-none">Error details</summary>
              <pre className="mt-2 overflow-auto rounded bg-muted p-2 text-xs">
                {this.state.error?.message}
              </pre>
            </details>
            <button
              className="mt-4 rounded bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/90"
              onClick={() => this.setState({ hasError: false, error: null })}
            >
              Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}