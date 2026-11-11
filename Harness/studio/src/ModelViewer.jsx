import React, {useEffect, useRef, useState} from 'react';
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {RotateCcw, Move, Box, LoaderCircle} from 'lucide-react';

export default function ModelViewer({url,cover,name,interactive=true}){
 const host=useRef(null),reset=useRef(null);const [state,setState]=useState('loading');
 useEffect(()=>{
  if(!url){setState('empty');return;}
  const el=host.current;if(!el)return;let renderer,scene,camera,controls,frame,disposed=false;const objects=[];setState('loading');
  try{
   renderer=new THREE.WebGLRenderer({antialias:true,alpha:true,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.setClearColor(0,0);renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
   renderer.domElement.setAttribute('aria-label',`${name} 三维模型，可拖动或用方向键旋转，用滚轮或加减键缩放`);renderer.domElement.setAttribute('role','img');renderer.domElement.tabIndex=interactive?0:-1;el.appendChild(renderer.domElement);
   scene=new THREE.Scene();camera=new THREE.PerspectiveCamera(35,1,0.001,1000);controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.dampingFactor=.08;controls.enablePan=false;controls.enabled=interactive;controls.minPolarAngle=.1;controls.maxPolarAngle=Math.PI*.88;const renderHidden=()=>{if(document.hidden)renderer.render(scene,camera)};controls.addEventListener('change',renderHidden);
   scene.add(new THREE.HemisphereLight(0xffffff,0x8b9188,2.8));const key=new THREE.DirectionalLight(0xffffff,4);key.position.set(3,5,4);scene.add(key);const fill=new THREE.DirectionalLight(0xe7eddf,2);fill.position.set(-3,1,-2);scene.add(fill);
   const keyboard=e=>{if(!interactive||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','-','='].includes(e.key))return;e.preventDefault();const offset=camera.position.clone().sub(controls.target),spherical=new THREE.Spherical().setFromVector3(offset);if(e.key==='ArrowLeft')spherical.theta-=.12;if(e.key==='ArrowRight')spherical.theta+=.12;if(e.key==='ArrowUp')spherical.phi=Math.max(.1,spherical.phi-.12);if(e.key==='ArrowDown')spherical.phi=Math.min(Math.PI*.88,spherical.phi+.12);if(e.key==='+'||e.key==='=')spherical.radius=Math.max(controls.minDistance,spherical.radius*.9);if(e.key==='-')spherical.radius=Math.min(controls.maxDistance,spherical.radius*1.1);camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(spherical));controls.update()};renderer.domElement.addEventListener('keydown',keyboard);
   const resize=()=>{if(disposed)return;const w=el.clientWidth,h=el.clientHeight;renderer.setSize(w,h,false);camera.aspect=w/Math.max(h,1);camera.updateProjectionMatrix()};const observer=new ResizeObserver(resize);observer.observe(el);resize();
   new GLTFLoader().load(url,(g)=>{
    if(disposed){g.scene.traverse(o=>{o.geometry?.dispose();if(o.material)(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>m.dispose())});return;}
    const model=g.scene;objects.push(model);const box=new THREE.Box3().setFromObject(model);if(box.isEmpty()){setState('error');return;}const size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());model.position.sub(center);scene.add(model);const scale=Math.max(size.x,size.y,size.z,.001);camera.near=scale/100;camera.far=scale*100;camera.updateProjectionMatrix();controls.minDistance=scale*.8;controls.maxDistance=scale*8;
    const initial=new THREE.Vector3(scale*1.5,scale*1.1,scale*1.8);reset.current=()=>{camera.position.copy(initial);controls.target.set(0,0,0);controls.update()};reset.current();renderer.render(scene,camera);setState('ready');
   },undefined,()=>{if(!disposed)setState('error')});
   const tick=()=>{if(disposed)return;controls.update();renderer.render(scene,camera);frame=requestAnimationFrame(tick)};tick();
   return()=>{disposed=true;cancelAnimationFrame(frame);observer.disconnect();renderer.domElement.removeEventListener('keydown',keyboard);controls.removeEventListener('change',renderHidden);controls.dispose();objects.forEach(obj=>obj.traverse(o=>{o.geometry?.dispose();if(o.material)(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>{Object.values(m).forEach(v=>v?.isTexture&&v.dispose());m.dispose()})}));renderer.dispose();renderer.domElement.remove();reset.current=null;};
  }catch{setState('error');renderer?.dispose();}
 },[url,interactive,name]);
 return <div className={`model-viewer model-${state}`}>
   <div ref={host} className="model-canvas"/>
   {(state==='empty'||state==='error')&&(cover?<img className="model-fallback" src={cover} alt={`${name} 模型预览`}/>:<div className="model-empty"><Box size={48} strokeWidth={1}/><span>{state==='error'?'三维预览暂不可用':'模型预览待生成'}</span></div>)}
   {state==='loading'&&<div className="model-loading"><LoaderCircle className="spin" size={22}/><span>载入模型</span></div>}
   {state==='ready'&&interactive&&<><div className="model-hint"><Move size={14}/> 拖动旋转 · 滚动缩放</div><button className="icon-button model-reset" onClick={()=>reset.current?.()} aria-label="重置模型视角" title="重置视角"><RotateCcw size={17}/></button></>}
   {state==='error'&&cover&&<span className="model-hint">静态预览 · 三维模型加载失败</span>}
 </div>
}
