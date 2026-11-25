const express = require('express');
const mineflayer = require('mineflayer');
const { pathfinder, Movements, goals } = require('mineflayer-pathfinder');

const CONFIG = {
  host: process.env.MC_HOST || 'UmbralSMP.aternos.me',
  port: Number(process.env.MC_PORT || 12081),
  username: process.env.BOT_USERNAME || 'TASLIMA',
  version: process.env.MC_VERSION || false,
  auth: process.env.MC_AUTH || 'offline'
};
const DASHBOARD_PORT = Number(process.env.PORT || 3000);
const FOOD_LEVEL = 16, FOLLOW_DISTANCE = 2, WANDER_RADIUS = 5;
const WANDER_INTERVAL = 3000;  // proti 3 second-e notun jaygay move korbe
const DEFEND_RADIUS = 5, DEFEND_MIN_HEALTH = 10;
const RECONNECT_MIN = 10000, RECONNECT_MAX = 120000;
const STUCK_MOVE_MIN = 0.25;   // 1 second-e eta kom norle "atke gese"
const STUCK_TICKS = 3;         // koyta tick atke thakle sidestep korbe

const app = express();
const status = {online:false, username:CONFIG.username, server:`${CONFIG.host}:${CONFIG.port}`,
  since:null, lastReason:null, reconnects:0, mode:'offline', health:null, food:null, lastAction:'Starting', unstuckCount:0};
app.get('/', (_req,res)=>res.type('html').send(`<h2>TASLIMA Bot</h2>
<p>Status: <b>${status.online?'ONLINE':'OFFLINE'}</b></p><p>Mode: ${status.mode}</p>
<p>Health: ${status.health??'-'}</p><p>Food: ${status.food??'-'}</p>
<p>Reconnects: ${status.reconnects}</p><p>Unstuck: ${status.unstuckCount}</p>
<p>Last action: ${status.lastAction}</p><p>Last disconnect: ${status.lastReason||'none'}</p>`));
app.get('/status',(_req,res)=>res.json(status));
app.listen(DASHBOARD_PORT,'0.0.0.0',()=>console.log(`Dashboard: http://127.0.0.1:${DASHBOARD_PORT}`));

let bot=null, reconnectTimer=null, reconnectDelay=RECONNECT_MIN, stopping=false, actionBusy=false;
let defenseTimer=null, foodTimer=null, movementTimer=null, stuckTimer=null;
let followTarget=null, wanderGoalActive=false, unsticking=false;
let lastPos=null, stuckTicks=0, noPathCount=0;
const hostileNames=new Set(['zombie','husk','drowned','skeleton','stray','bogged','creeper','spider','cave_spider','witch','pillager','vindicator','evoker','ravager','phantom','slime','magma_cube','blaze','ghast','piglin_brute','hoglin','zoglin','warden','silverfish','endermite']);

const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function logAction(s){status.lastAction=s;console.log(s);}
function clearLoops(){[defenseTimer,foodTimer,movementTimer,stuckTimer].forEach(t=>{if(t)clearInterval(t);});defenseTimer=foodTimer=movementTimer=stuckTimer=null;}
function stopPath(){try{if(bot?.pathfinder)bot.pathfinder.setGoal(null);}catch(_){}}
function wanderMode(){followTarget=null;wanderGoalActive=false;status.mode='wandering';stopPath();logAction('Wander mode enabled');}
function isHostile(e){return !!e&&e.type==='mob'&&!!e.name&&hostileNames.has(e.name.toLowerCase());}

function startWandering(){
  if(!bot?.entity||followTarget||unsticking||status.mode==='staying')return;
  // Beshi bar atkle choto radius-e ghurbe
  const radius=noPathCount>=2?4:WANDER_RADIUS;
  const p=bot.entity.position, x=Math.floor(p.x+(Math.random()*2-1)*radius), z=Math.floor(p.z+(Math.random()*2-1)*radius);
  try{bot.pathfinder.setGoal(new goals.GoalNearXZ(x,z,1));wanderGoalActive=true;status.mode='wandering';logAction(`Wandering toward ${x}, ${z}`);}
  catch(e){logAction(`Wander error: ${e.message}`);}
}

// Atke gele bame/dane sore jabe, lafabe, tarpor abar notun path nibe. Kono block bhangbe na.
async function unstick(reason){
  if(unsticking||!bot?.entity||status.mode==='staying')return;
  unsticking=true;stuckTicks=0;status.unstuckCount++;
  const side=Math.random()<0.5?'left':'right';
  logAction(`Stuck (${reason}); sidestep ${side}`);
  try{
    stopPath();
    bot.clearControlStates();
    await bot.look(bot.entity.yaw+(Math.random()<0.5?1:-1)*(Math.PI/3+Math.random()*Math.PI/3),0,true);
    bot.setControlState(side,true);bot.setControlState('jump',true);
    await sleep(600);
    bot.clearControlStates();
    if(Math.random()<0.5){bot.setControlState('back',true);await sleep(400);bot.clearControlStates();}
    bot.setControlState('forward',true);bot.setControlState('jump',true);
    await sleep(1200);
  }catch(e){console.log('Unstick error:',e.message);}
  finally{
    try{bot.clearControlStates();}catch(_){}
    unsticking=false;lastPos=null;
    if(followTarget)followPlayer(followTarget,false);
    else if(status.mode==='wandering')startWandering();
  }
}

function checkStuck(){
  if(!bot?.entity||unsticking||actionBusy)return;
  const pos=bot.entity.position.clone();
  let wantsMove=false;
  if(followTarget){
    const p=bot.players[followTarget];
    wantsMove=!!p?.entity&&pos.distanceTo(p.entity.position)>FOLLOW_DISTANCE+2;
  }else if(status.mode==='wandering'){
    wantsMove=wanderGoalActive;
  }
  if(!wantsMove){stuckTicks=0;lastPos=pos;return;}
  if(lastPos&&pos.distanceTo(lastPos)<STUCK_MOVE_MIN)stuckTicks++;
  else{stuckTicks=0;noPathCount=0;}
  lastPos=pos;
  if(stuckTicks>=STUCK_TICKS)unstick('not moving');
}

async function eatIfHungry(){
  if(!bot?.entity||actionBusy||unsticking||bot.food==null||bot.food>FOOD_LEVEL)return;
  const food=bot.inventory.items().find(i=>/bread|cooked_|golden_apple|apple|carrot|potato|beetroot|melon|sweet_berries|glow_berries|cookie|pumpkin_pie|mushroom_stew|rabbit_stew|beetroot_soup|honey_bottle/.test(i.name));
  if(!food){logAction('Hungry: no food in inventory');return;}
  actionBusy=true;try{await bot.equip(food,'hand');await bot.consume();logAction(`Ate ${food.name}`);}
  catch(e){logAction(`Could not eat: ${e.message}`);}finally{actionBusy=false;}
}
async function defendNearby(){
  if(!bot?.entity||actionBusy||unsticking||bot.health==null||bot.health<DEFEND_MIN_HEALTH)return;
  const target=Object.values(bot.entities).filter(e=>isHostile(e)&&e.position&&bot.entity.position.distanceTo(e.position)<=DEFEND_RADIUS)
    .sort((a,b)=>bot.entity.position.distanceTo(a.position)-bot.entity.position.distanceTo(b.position))[0];
  if(!target)return;
  const sword=bot.inventory.items().filter(i=>/_sword$/.test(i.name)).sort((a,b)=>{
    const rank=n=>({netherite:6,diamond:5,iron:4,stone:3,golden:2,wooden:1}[n.split('_')[0]]||0);
    return rank(b.name)-rank(a.name);
  })[0];
  if(!sword){logAction(`Hostile nearby (${target.name}); no sword in inventory`);return;}
  actionBusy=true;try{await bot.equip(sword,'hand');bot.attack(target);logAction(`Defending against ${target.name}`);}
  catch(e){logAction(`Defense error: ${e.message}`);}finally{actionBusy=false;}
}
function followPlayer(name,reply=true){
  const p=bot.players[name];
  if(!p?.entity){if(reply)bot.chat(`I cannot see ${name} nearby. Come closer and try again.`);return false;}
  followTarget=name;wanderGoalActive=false;status.mode=`following ${name}`;
  bot.pathfinder.setGoal(new goals.GoalFollow(p.entity,FOLLOW_DISTANCE),true);
  if(reply)bot.chat(`Following ${name}.`);logAction(`Following ${name}`);return true;
}
function handleChat(username,message){
  if(!bot||username===bot.username)return;
  const parts=message.trim().split(/\s+/), cmd=(parts[0]||'').toLowerCase();
  if(cmd==='!help')bot.chat('Commands: !come, !follow <player>, !wander, !stop, !stay, !status');
  else if(cmd==='!come')followPlayer(username);
  else if(cmd==='!follow'&&parts[1])followPlayer(parts[1]);
  else if(cmd==='!wander'){wanderMode();bot.chat('I will wander around.');startWandering();}
  else if(cmd==='!stop'){wanderMode();bot.chat('Stopped following; wandering nearby.');startWandering();}
  else if(cmd==='!stay'){followTarget=null;status.mode='staying';wanderGoalActive=false;stopPath();bot.chat('I will stay here.');logAction('Stay mode');}
  else if(cmd==='!status')bot.chat(`Health ${Math.round(bot.health??0)}, food ${bot.food??0}, mode ${status.mode}`);
}
function scheduleReconnect(reason){
  status.online=false;status.lastReason=String(reason||'Connection ended');status.mode='offline';clearLoops();
  if(stopping||reconnectTimer)return;
  console.log(`Disconnected: ${status.lastReason}. Retry in ${Math.round(reconnectDelay/1000)}s`);
  reconnectTimer=setTimeout(()=>{reconnectTimer=null;status.reconnects++;createBot();},reconnectDelay);
  reconnectDelay=Math.min(Math.round(reconnectDelay*1.5),RECONNECT_MAX);
}
function createBot(){
  if(stopping)return;
  console.log(`Connecting to ${CONFIG.host}:${CONFIG.port} as ${CONFIG.username}...`);
  unsticking=false;lastPos=null;stuckTicks=0;noPathCount=0;
  try{bot=mineflayer.createBot(CONFIG);}catch(e){scheduleReconnect(e.message);return;}
  bot.loadPlugin(pathfinder);
  bot.dig=()=>Promise.reject(new Error('Digging disabled'));  // kono block bhangar chesta-i korbe na
  bot.once('spawn',()=>{
    status.online=true;status.since=new Date().toISOString();reconnectDelay=RECONNECT_MIN;
    const movements=new Movements(bot);
    movements.canDig=false;            // kono block bhangbe na
    movements.allow1by1towers=false;   // block boshiye uthbe na
    movements.allowParkour=false;
    movements.allowSprinting=false;
    movements.scafoldingBlocks=[];     // block place korbe na
    bot.pathfinder.setMovements(movements);
    bot.pathfinder.thinkTimeout=3000;  // path khujte beshi somoy nibe na
    status.mode='wandering';logAction('Joined server; random movement starting');
    foodTimer=setInterval(()=>{status.health=bot.health;status.food=bot.food;eatIfHungry().catch(e=>console.log(e.message));},4000);
    defenseTimer=setInterval(()=>{
      defendNearby().catch(e=>console.log(e.message));
      if(unsticking)return;
      if(followTarget){const p=bot.players[followTarget];if(p?.entity)bot.pathfinder.setGoal(new goals.GoalFollow(p.entity,FOLLOW_DISTANCE),true);
        else{const lost=followTarget;followTarget=null;wanderMode();bot.chat(`Lost sight of ${lost}; wandering again.`);}}
    },1500);
    movementTimer=setInterval(()=>{if(!unsticking&&!followTarget&&status.mode==='wandering')startWandering();},WANDER_INTERVAL);
    stuckTimer=setInterval(checkStuck,1000);
    setTimeout(startWandering,1200);
  });
  bot.on('goal_reached',()=>{wanderGoalActive=false;noPathCount=0;});
  bot.on('path_update',r=>{
    if(r.status==='noPath'||r.status==='timeout'){
      noPathCount++;wanderGoalActive=false;
      if(!followTarget&&status.mode==='wandering')setTimeout(()=>unstick('no path'),300);
    }
  });
  bot.on('health',()=>{status.health=bot.health;status.food=bot.food;});
  bot.on('death',()=>{logAction('Died; attempting respawn');setTimeout(()=>{try{if(bot?.entity&&bot.health<=0)bot.respawn();}catch(e){console.log(e.message);}},1500);});
  bot.on('chat',handleChat);
  bot.on('kicked',r=>{const s=typeof r==='string'?r:JSON.stringify(r);status.lastReason=`Kicked: ${s}`;console.log(status.lastReason);});
  bot.on('error',e=>console.log('Bot error:',e.message));
  bot.on('end',scheduleReconnect);
}
function shutdown(){if(stopping)return;stopping=true;clearLoops();if(reconnectTimer)clearTimeout(reconnectTimer);try{if(bot)bot.quit('Stopped from Termux');}catch(_){}console.log('Bot stopped.');setTimeout(()=>process.exit(0),700);}
process.on('SIGINT',shutdown);process.on('SIGTERM',shutdown);
process.on('uncaughtException',e=>console.log('Uncaught exception:',e.message));
process.on('unhandledRejection',e=>console.log('Unhandled rejection:',e?.message||e));
createBot();
