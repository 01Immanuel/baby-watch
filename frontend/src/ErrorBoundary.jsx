import { Component } from 'react'

// Last line of defence: a crash must never leave a blank screen in a safety tool.
export default class ErrorBoundary extends Component {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div style={{ maxWidth: '30rem', margin: '15vh auto', padding: 24, fontFamily: 'system-ui, sans-serif', lineHeight: 1.5 }}>
        <h1 style={{ fontSize: '1.5rem' }}>Something went wrong</h1>
        <p>Reload the page. If a pregnant woman has bleeding, fits, severe headache or severe belly pain, go to a health facility now.</p>
        <button type="button" onClick={() => window.location.reload()} style={{ font: 'inherit', padding: '12px 20px', borderRadius: 12, border: 0, background: '#1D4FD7', color: '#fff', fontWeight: 700 }}>Reload</button>
      </div>
    )
  }
}
