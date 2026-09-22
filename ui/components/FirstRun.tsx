import { Modal } from './PanelFrame';

export function FirstRun({onDone,onConfigure}:{onDone:()=>void;onConfigure:()=>void}) {
  return <Modal title="Welcome to Stonic" subtitle="Your personal workspace is ready to set up." onClose={onDone}><div className="modal-content">
    <h3>Start with text</h3><p>Notes, reminders, tasks and local files work on this device. Save your xKiro key in Configuration to enable intelligence and live research.</p>
    <h3>Connect intelligence</h3><p>Open AI &amp; Providers to save your xKiro key, choose the exact model identifier, and test the saved connection. Temporary provider failures do not erase your saved credential.</p>
    <h3>You review sensitive actions</h3><p>File changes, computer input, screen inspection and code execution pause for review in Task activity. Images go to xKiro only after you approve that upload.</p>
    <div className="action-row"><button className="primary-button" onClick={onConfigure}>Open AI setup</button><button className="secondary-button" onClick={onDone}>Start workspace</button></div>
  </div></Modal>;
}
