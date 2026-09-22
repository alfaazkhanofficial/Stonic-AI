import { useState } from 'react';
import { api } from '../api';

export function VisionPanel({imageUrl}: {imageUrl: string}) {
  const [question, setQuestion] = useState('Describe what is visible and explain any problems.'), [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [result, setResult] = useState('');
  async function process(mode: 'ocr'|'analyze') {
    setBusy(true); setError('');
    try {
      let data = imageUrl;
      if (!data.startsWith('data:')) {
        const blob = await (await fetch(imageUrl)).blob();
        data = await new Promise<string>((resolve, reject) => {const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(new Error('Image could not be read.')); reader.readAsDataURL(blob);});
      }
      const response = await api<{data: {text: string}}>('/vision', {method:'POST', body:JSON.stringify({image:data, question, mode, consent_to_upload:consent})});
      setResult(response.data.text || 'No readable text was found in this image.');
    } catch(e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  return <div className="domain-content">{imageUrl ? <><img className="vision-review-image" src={imageUrl} alt="Image selected for analysis"/><label>What would you like to understand?<input value={question} onChange={e => setQuestion(e.target.value)} maxLength={3000}/></label><label className="checkbox-line"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)}/><span>Allow this image to be sent to xKiro for analysis.</span></label><div className="action-row"><button className="secondary-button" disabled={busy} onClick={() => void process('ocr')}>Extract text locally</button><button className="primary-button" disabled={busy || !consent} onClick={() => void process('analyze')}>{busy ? 'Processing…' : 'Analyze with xKiro'}</button></div></> : <p className="muted">Capture your screen or import an image into the Visual Hub first.</p>}{error && <p role="alert" className="error-box">{error}</p>}{result && <div className="report-text" role="status">{result}</div>}</div>;
}
