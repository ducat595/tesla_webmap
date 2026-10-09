const assert=require('node:assert/strict');const N=require('../frontend/nav-core.js');
assert.deepEqual(N.parseCoordinates('35.6812,139.7671'),[35.6812,139.7671]);assert.equal(N.parseCoordinates('東京駅'),null);assert.throws(()=>N.parseCoordinates('91,0'));
const path=[[35,139],[35,139.001],[35.001,139.001]],cum=N.cumulative(path);assert(cum[2]>190&&cum[2]<210);const p=N.project([35,139.0005],path,cum);assert(p.gap<1);assert(Math.abs(p.along-cum[1]/2)<1);
const off=N.project([35.01,139.01],path,cum);assert(off.gap>1000);assert.equal(N.project([35,139.0001],path,cum,150,160),null);
assert(N.instruction({type:'turn',modifier:'left'},'国道').includes('左折'));assert(N.instruction({type:'roundabout',exit:2}).includes('2番目'));assert.equal(N.instruction({type:'arrive'}),'目的地に到着');
console.log('座標入力・ルートへの投影・距離・案内文のテスト成功');
