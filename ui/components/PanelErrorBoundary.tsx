import { Component, type ReactNode } from 'react';

export class PanelErrorBoundary extends Component<{children:ReactNode;title:string},{failed:boolean}> {
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  render(){return this.state.failed?<div className="modal-content" role="alert"><h3>{this.props.title} needs to reload</h3><p>Your saved data remains available. Other panels can still be used.</p><button className="secondary-button" onClick={()=>this.setState({failed:false})}>Reload this panel</button></div>:this.props.children;}
}
