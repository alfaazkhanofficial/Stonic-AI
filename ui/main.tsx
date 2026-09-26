import { Component, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';

class ErrorBoundary extends Component<{children: ReactNode}, {error: boolean}> {
  state = { error: false };
  static getDerivedStateFromError() { return { error: true }; }
  render() {
    return this.state.error ? <div className="fatal-error"><h1>The workspace needs to reload.</h1><p>Your saved notes, tasks, and settings remain on this device.</p><button onClick={() => location.reload()}>Reload workspace</button></div> : this.props.children;
  }
}

createRoot(document.getElementById('root')!).render(<ErrorBoundary><App/></ErrorBoundary>);
