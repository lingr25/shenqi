# 统一知识库检索评测报告

- 语料: kb/docs.jsonl **25021** 条 (已排除 noise)
- 评分: bigram BM25 × retrieval_boost × retrieval_weight
- 手写题命中: **22/22**
- 手写题 top3 轨道: {'vod_official': 31, 'qq': 30, 'vod_cloud': 5}

## 寻路第一步按什么顺序推地块
(vod 算法课定论; 期望: 上右下左)
1. [vod_entry|vod_only] # 寻路地图的初始遍历与来源记录
2. [vod_atom|vod_only] 寻路从路径点所在格开始，按上、右、下、左的顺序推地块
3. [vod_entry|vod_only] # E2 后下一步能否生成 F1
4. [vod_atom|vod_only] 已经被排过一次的格子不再排
5. [vod_atom|vod_only] 按该顺序遍历，直到排完所有可通行地块
判定: HIT; top5 轨道: Counter({'vod_official': 5})

## 开120帧会让费用条更精确吗
(vod 辟谣; 期望: 逻辑帧/画面帧)
1. [vod_entry|vod_only] # 120帧显示与逻辑帧/费用尺精度
2. [vod_atom|vod_only] 开120帧不会给费用尺加精度
3. [vod_atom|vod_only] 开启的120帧是单纯画面，既不动动画帧也不动逻辑帧
4. [vod_atom|vod_only] 开120帧费用尺不会加精度
5. [vod_atom|vod_only] 逻辑帧是可以影响费用尺的东西
判定: HIT; top5 轨道: Counter({'vod_official': 5})

## M3同帧部署奶谁
(vod conflict 两面召回; 期望: M3/奶)
1. [vod_entry|vod_only] # 同帧部署转正后其他特例异常（M3、门、刁民船、代理）
2. [vod_entry|vod_only] # M3多目标治疗/仇恨索敌目标的判定排序
3. [qq_window|group_only] 娜斯提高台与干员同帧/差帧部署限制
4. [qq_canonical|n/a] 同帧部署仇恨增量与同仇恨先创建
5. [vod_atom|vod_only] 同帧部署时打先部署
判定: HIT; top5 轨道: Counter({'vod_official': 3, 'qq': 2})

## 索敌是三帧一索吗
(vod 辟谣; 期望: 三帧/三针)
1. [vod_entry|vod_only] # 迷迭香三帧索敌说法的来源
2. [vod_atom|vod_only] 索敌是三帧索敌，索敌周期为三帧
3. [vod_atom|vod_only] 索敌是三帧索敌
4. [qq_window|group_only] 通用三帧索敌机制与缪缪等特例
5. [vod_entry|vod_only] # 战车动画长度与三帧索敌冷却
判定: HIT; top5 轨道: Counter({'vod_official': 2, 'vod_cloud': 2, 'qq': 1})

## 落地隐切换帧是第几帧
(vod conflict; 期望: 落地隐)
1. [qq_atom|group_only] 触发2天赋时，落地隐身结束切换发生在第52帧。
2. [qq_window|group_only] 落地隐身帧数与技能开启、索敌判定时间点
3. [vod_atom|vod_only] 第三十一帧是落地隐切换的帧。
4. [qq_window|group_only] EW落地隐匿与魂灵之影迷彩的帧内结算顺序
5. [qq_atom|group_only] 能开启技能的时间点就是落地隐身结束切换的帧数。
判定: HIT; top5 轨道: Counter({'qq': 4, 'vod_cloud': 1})

## 穿刺花生命比例相同时看仇恨吗
(vod conflict; 期望: 穿刺花)
1. [vod_entry|vod_only] # 穿刺花生命比例相同时的仇恨索敌机制
2. [vod_atom|vod_only] 若范围内生命比例相同，则睡眠索敌看仇恨
3. [vod_atom|vod_only] 现在测出来穿刺花在我方生命比例相同时索敌会看仇恨
4. [vod_atom|vod_only] 以前测试过穿刺花在我方生命比例相同时索敌不会看仇恨
5. [vod_cluster|vod_only] 穿刺花在生命比例相同时是否看仇恨
判定: HIT; top5 轨道: Counter({'vod_official': 5})

## 冷却计时器剩余多少判定归零
(vod 推导链; 期望: 冷却/归零)
1. [vod_entry|vod_only] # 费用/冷却计时器的归零判定、过费与残余冷却机制
2. [vod_entry|vod_only] # 冷却计时器机制与费用冷却行为
3. [vod_atom|vod_only] 冷却精确记成小数点
4. [vod_atom|vod_only] 冷却是一个可以小于零也可以大于零的数
5. [vod_atom|vod_only] 冷却可以大于一，虽然冷却总长度是一
判定: HIT; top5 轨道: Counter({'vod_cloud': 3, 'vod_official': 2})

## 城防炮索敌精度是多少
(vod 精度条件; 期望: 城防炮)
1. [vod_entry|vod_only] # 萨米双王左右盾位下城防炮与青金索敌差异
2. [vod_entry|vod_only] # 城防炮在零帧部署一帧撤退下的普攻/技能索敌帧
3. [vod_atom|vod_only] 双王的城防炮就是因为0.001精度从而可以索敌左大盾
4. [vod_entry|vod_only] # 同帧部署转正后萨米城防炮索敌异常
5. [vod_entry|vod_only] # 决战技与伦蒂尼姆城防炮的索敌及切模式机制
判定: HIT; top5 轨道: Counter({'vod_official': 5})

## 嘲讽和锁敌表现是不是反了
(vod 版本相关; 期望: 嘲讽/颠倒)
1. [qq_window|also_in_vod] 浮士德嘲讽异常与仇恨疑似封顶
2. [vod_entry|vod_only] # 仇恨乱序与索敌的关系
3. [qq_canonical|n/a] 嘲讽等级上限、属性机制与特殊地形仇恨抵消
4. [qq_window|also_in_vod] 嘲讽机制数值与仇恨异常表现
5. [qq_window|unknown] 正负嘲讽差异、挂嘲讽与浮士德过滤器
判定: HIT; top5 轨道: Counter({'qq': 4, 'vod_official': 1})

## 同仇恨时打先创建还是后创建的
(vod conflict; 期望: 创建)
1. [vod_entry|vod_only] # 敌人仇恨与同仇恨创建顺序
2. [vod_entry|vod_only] # 同仇恨/无法排序时的先后规则
3. [vod_entry|vod_only] # 索敌流程与攻击目标决定机制
4. [qq_canonical|n/a] 长时间部署仇恨相同判定与创建顺序规则
5. [qq_window|conflict] 索敌仇恨距离精度为0.1格与同仇恨优先判定
判定: HIT; top5 轨道: Counter({'vod_official': 3, 'qq': 2})

## 夜半眠兽撤退后睡眠什么时候解除
(qq window w000006; 期望: 眠兽/睡眠)
1. [qq_window|group_only] 夜半眠兽撤退与开技能出睡帧时序
2. [qq_atom|group_only] 夜半的眠兽撤退时睡眠状态直接消失。
3. [qq_window|group_only] 夜半眠兽索敌机制与控人逻辑
4. [qq_atom|group_only] 夜半的眠兽重生时立刻生效。
5. [vod_entry|vod_only] # 卡夫卡与夜半睡眠结束后的行动与无缝控部署
判定: HIT; top5 轨道: Counter({'qq': 4, 'vod_official': 1})

## 祥子的攻击类型按阻挡还是按地面飞行判定
(qq window w000136; 期望: 阻挡)
1. [qq_window|also_in_vod] 祥子攻击方式机制判定与攻击间隔帧数争议
2. [qq_atom|group_only] 祥子的攻击类型机制上应按阻挡/非阻挡进行区分而非套用地面/飞行分类
3. [vod_entry|vod_only] # 攻击间隔与换阻挡抬手影响机制
4. [qq_window|group_only] 酒神牢笼阻挡类型与围栏阻挡禁令交互
5. [vod_entry|vod_only] # 飞行单位与坑杀判定
判定: HIT; top5 轨道: Counter({'qq': 3, 'vod_official': 2})

## 传送带的位移本质是修改速度还是传送
(qq window w001356; 期望: 传送带)
1. [qq_window|group_only] 传送带位移机制推析与避障交互
2. [qq_window|also_in_vod] 诱导/恐惧的目标速度改写与传送带的每帧坐标重写机制
3. [qq_atom|group_only] 单纯修改速度无法做到敌人在抬手期间仍在传送带上位移。
4. [qq_window|also_in_vod] 山3技能传送带机制与位移本质
5. [qq_canonical|n/a] 传送带、阻挡偏移与寻路能否共存
判定: HIT; top5 轨道: Counter({'qq': 5})

## 空A为什么看起来连A两下
(qq window w000141; 期望: 前摇)
1. [qq_window|conflict] 空A前摇差异导致视觉连A与Boss战帧率时间流速机制
2. [qq_atom|group_only] 视觉上的连A两下并非索敌重置普攻或模式切换
3. [vod_entry|vod_only] # 塞雷娅出奶后索敌时序与攻速加帧机制
4. [vod_entry|vod_only] # 无目标时整间隔前摇加一帧保底后摇
5. [vod_atom|vod_only] 离开不可通行地块之前走不可通行地块那一套逻辑，离开之后走之外那一套，看起来连贯只是因为数值没什么区别
判定: HIT; top5 轨道: Counter({'vod_official': 3, 'qq': 2})

## H17-3右上角的花能挤偏移入坑吗
(qq window w000081; 期望: H17-3/偏移)
1. [qq_atom|group_only] 通过挤压从第二个花开始无法使H17-3右上角敌人发生阻挡偏移入坑
2. [vod_entry|vod_only] # 阻挡偏移与传送的落点、速度与持续时间特性
3. [vod_entry|vod_only] # 空间与敌人坐标的细分
4. [vod_entry|vod_only] # 阻挡偏移坐标测试方法与偏移机制
5. [vod_entry|vod_only] # 阻挡偏移的定义与期间效果
判定: HIT; top5 轨道: Counter({'vod_official': 4, 'qq': 1})

## 索敌帧是什么
(glossary; 期望: 索敌帧)
1. [vod_entry|vod_only] # 普通干员被索敌帧31/32与同帧创建顺序
2. [qq_window|also_in_vod] 灵知平A索敌帧限制与前摇帧数浮动
3. [qq_window|also_in_vod] 攻击间隔与出伤间隔的前摇波动实测表现
4. [vod_entry|vod_only] # 酒神索敌帧余数随打一下的平移
5. [vod_entry|vod_only] # 测试干员索敌帧的方法
判定: HIT; top5 轨道: Counter({'vod_official': 3, 'qq': 2})

## 平整化算法是什么
(glossary/shenqi slang; 期望: 平整化)
1. [vod_atom|vod_only] 鹰角会用平整化算法拉直路线
2. [vod_atom|vod_only] 平整化算法要判定障碍物
3. [qq_window|also_in_vod] 寻路平整化判定的缺陷与尺寸触发条件
4. [vod_atom|vod_only] 拉直目前可简化为：鹰角会尽可能把走的连线拉直到尽可能远
5. [qq_atom|group_only] 寻路平整化问题是由官方平整化算法实现存在缺陷导致的。
判定: HIT; top5 轨道: Counter({'vod_official': 3, 'qq': 2})

## 隐匿和迷彩有什么区别
(glossary 消歧; 期望: 隐匿/迷彩)
1. [qq_window|group_only] 干员落地迷彩生效时机与忍冬/卡夫卡机制
2. [qq_canonical|n/a] 索敌双方属性对抗机制与隐匿/伪装/无敌检测判定
3. [qq_window|group_only] EW落地隐匿与魂灵之影迷彩的帧内结算顺序
4. [qq_atom|group_only] 在实战中，风雪之眼效果结束时挂上的反隐效果除永续隐匿和迷彩外影响较小。
5. [qq_atom|group_only] 同一帧内解除落地隐匿与获得迷彩不等于完全无缝。
判定: HIT; top5 轨道: Counter({'qq': 5})

## visitNodeCenter是什么
(glossary 拆包; 期望: visitNodeCenter)
1. [glossary|n/a] visitNodeCenter
2. [qq_atom|group_only] visitnodecenter 启动后会强制敌人进入拐角格 0.05 半径之内。
3. [qq_atom|group_only] 目前没有任何敌人实装使用 visitnodecenter。
4. [qq_window|group_only] 敌人拐弯寻路逻辑、避障力及中心对齐配置（visitnodecenter/visittilecenter）
5. [qq_canonical|n/a] 拐弯寻路、避障力与中心对齐配置
判定: HIT; top5 轨道: Counter({'qq': 5})

## 重构体撤退返还费用吗
(conflict vod_wins w000416; 期望: 重构体/撤退)
1. [qq_window|conflict] 重构体死亡/撤退动画与干员撤退机制差异
2. [qq_atom|conflict] 弧光跳跃判定依据的是重构体播放的撤退/死亡动画。
3. [vod_entry|vod_only] # 控制重构体部署轴的可行性与费用
4. [vod_entry|vod_only] # 重构体死亡动画窗口与M3索敌
5. [vod_entry|vod_only] # M3开技能同帧撤重构体的卡死与跳转行为
判定: HIT; top5 轨道: Counter({'vod_official': 3, 'qq': 2})

## 位移和伤害的结算顺序是什么
(conflict vod_wins w000554; 期望: 位移/结算)
1. [qq_window|group_only] 同帧命中时的伤害结算顺序与连续/首次攻击差异
2. [vod_entry|vod_only] # 弹道/无弹道推拉差异与结算顺序
3. [qq_window|group_only] 传送带同帧结算顺序与浮空前移动现象
4. [qq_window|group_only] 代理与手动撤退的位移差异为同帧结算顺序不同
5. [qq_atom|also_in_vod] 弹道位移的结算顺序是先命中后失衡。
判定: HIT; top5 轨道: Counter({'qq': 4, 'vod_official': 1})

## 冷却在部署前就开始转吗
(conflict vod_wins w001186; 期望: 冷却)
1. [qq_window|also_in_vod] 攻击冷却计时起点与索敌间隔关系
2. [vod_entry|vod_only] # 费用条异常(Fee Bar Anomaly)出现的时间条件
3. [vod_atom|vod_only] 前十秒和后面不一样，前十秒指的不只是局内的前十秒，而是费用从清空开始转、费用冷却从清空开始转的前十秒
4. [qq_atom|group_only] 祥子索敌后开始转攻击冷却。
5. [qq_window|group_only] 多堆叠单位的再部署冷却排队与UI显示机制
判定: HIT; top5 轨道: Counter({'qq': 3, 'vod_official': 1, 'vod_cloud': 1})

## 盲测题集(自动生成, expect_doc_id 命中)

- 题量: **74**
- Recall@5: **68/74** (92%)
- Recall@1: **52/74** (70%)

### MISS 清单(需分析)

- 游戏里干员技能条那个黄条是怎么算出来显示多长的？会不会一格一格跳？ → 期望 `vod_cluster:帧时序与计时器-1-3` (帧时序与计时器)
- 干员起飞的时候算不算挂隐匿啊？之前听主播说过这个事，到底是不是真的？ → 期望 `window:w001198` (干员机制)
- 避障力是拿什么来算判定区的？跟敌人的身位数据有关系吗？ → 期望 `vod_cluster:寻路-19-7` (寻路)
- M3切近战之后为啥不能马上A出去？那个锁敌的CD是怎么算的？ → 期望 `vod_cluster:索敌-18-7` (索敌)
- 萨尔贡那个本家终端为啥不吃攻速和盟约啊？打Boss是不是真的没用？还有至简和佩佩到底谁当C更好？ → 期望 `window:w001890` (数值与读图)
- 为啥我晕了那个飘在天上的怪它还不掉下来？是不是所有能飘的怪被晕了都会落地啊？ → 期望 `window:w001263` (位移)
