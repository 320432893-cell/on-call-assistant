#!/usr/bin/env python
# 数据初始化脚本：生成模拟SOP数据并导入

import os
import json
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent
DATA_RAW = BASE_DIR / "data" / "raw"

# 10份SOP文档数据
SOP_DOCUMENTS = [
    {
        "id": "sop-001",
        "title": "后端服务 On-Call SOP",
        "department": "后端服务",
        "tags": ["OOM", "服务超时", "降级策略", "故障分级"],
        "content": """
<h1>后端服务 On-Call SOP</h1>

<h2 id="oom">OOM 排查流程</h2>
<p>当服务出现OOM（Out of Memory）告警时，按以下步骤处理：</p>
<ol>
<li>立即查看内存使用趋势，确认是否持续上升</li>
<li>检查最近是否有大批量数据处理或内存泄漏代码变更</li>
<li>导出heap dump进行分析（jmap -dump:format=b,file=heap.hprof <pid>）</li>
<li>分析大对象分布，定位内存泄漏点</li>
<li>临时扩容或重启服务恢复业务</li>
<li>提交bug单，跟踪修复进度</li>
</ol>

<h2 id="timeout">服务超时处理</h2>
<p>服务超时常见原因：</p>
<ul>
<li>下游依赖响应慢</li>
<li>数据库查询慢</li>
<li>网络抖动</li>
<li>服务实例负载过高</li>
</ul>
<p>处理步骤：</p>
<ol>
<li>查看服务监控，确认超时接口和时间段</li>
<li>检查下游服务状态</li>
<li>必要时启用降级策略</li>
</ol>

<h2 id="degrade">降级策略</h2>
<p>触发条件：</p>
<ul>
<li>依赖服务不可用超过阈值时间</li>
<li>错误率超过设定阈值（如5%）</li>
<li>响应时间超过SLA</li>
</ul>
<p>降级方案：</p>
<ul>
<li>返回缓存数据</li>
<li>返回默认值或空结果</li>
<li>限流保护</li>
</ul>

<h2 id="level">故障分级</h2>
<table>
<tr><th>级别</th><th>定义</th><th>响应时间</th></tr>
<tr><td>P0</td><td>核心业务完全不可用</td><td>5分钟内响应</td></tr>
<tr><td>P1</td><td>核心业务部分受损</td><td>15分钟内响应</td></tr>
<tr><td>P2</td><td>非核心业务受影响</td><td>30分钟内响应</td></tr>
<tr><td>P3</td><td>轻微问题，不影响业务</td><td>工作时间处理</td></tr>
</table>
"""
    },
    {
        "id": "sop-002",
        "title": "数据库 DBA On-Call SOP",
        "department": "数据库DBA",
        "tags": ["主从延迟", "慢查询", "连接池满", "数据恢复"],
        "content": """
<h1>数据库 DBA On-Call SOP</h1>

<h2 id="replication-lag">主从延迟处理</h2>
<p>主从延迟超过30秒告警处理：</p>
<ol>
<li>检查主库写入QPS是否突增</li>
<li>检查从库负载和IO状态</li>
<li>检查是否存在大事务或长查询阻塞</li>
<li>必要时临时切换读流量到主库</li>
<li>评估是否需要增加从库或拆分读写</li>
</ol>

<h2 id="slow-query">慢查询优化</h2>
<p>慢查询定义：执行时间超过1秒的查询</p>
<p>排查步骤：</p>
<ol>
<li>从慢查询日志获取SQL语句</li>
<li>使用EXPLAIN分析执行计划</li>
<li>检查索引使用情况</li>
<li>检查是否存在全表扫描</li>
<li>优化SQL或添加索引</li>
</ol>

<h2 id="connection-pool">连接池满处理</h2>
<p>连接池满告警：</p>
<ol>
<li>检查当前连接数和来源</li>
<li>检查是否有连接泄漏（未释放）</li>
<li>检查是否有慢查询占用连接</li>
<li>临时调整连接池上限</li>
<li>通知业务方排查代码</li>
</ol>

<h2 id="data-recovery">数据恢复</h2>
<p>数据误删除/修改恢复：</p>
<ol>
<li>立即停止写入，评估影响范围</li>
<li>检查是否有备份可恢复</li>
<li>使用binlog进行point-in-time恢复</li>
<li>验证数据完整性后恢复服务</li>
</ol>
"""
    },
    {
        "id": "sop-003",
        "title": "前端 On-Call SOP",
        "department": "前端",
        "tags": ["页面白屏", "CDN资源加载失败", "兼容性", "性能劣化"],
        "content": """
<h1>前端 On-Call SOP</h1>

<h2 id="white-screen">页面白屏排查</h2>
<p>白屏常见原因：</p>
<ul>
<li>JS执行错误</li>
<li>资源加载失败（CDN问题）</li>
<li>接口返回异常数据</li>
<li>浏览器兼容性问题</li>
</ul>
<p>排查步骤：</p>
<ol>
<li>检查监控告警，确认白屏率和影响范围</li>
<li>获取用户浏览器信息和错误堆栈</li>
<li>检查最近发布版本是否有变更</li>
<li>必要时回滚版本</li>
</ol>

<h2 id="cdn-failure">CDN 资源加载失败</h2>
<p>CDN故障处理：</p>
<ol>
<li>检查CDN节点状态和响应时间</li>
<li>切换到备用CDN域名</li>
<li>联系CDN服务商排查</li>
<li>评估是否需要调整资源部署策略</li>
</ol>

<h2 id="compatibility">浏览器兼容性</h2>
<p>兼容性问题处理：</p>
<ul>
<li>确认影响浏览器版本范围</li>
<li>检查是否使用了不支持的API</li>
<li>添加polyfill或降级方案</li>
<li>更新browserslist配置</li>
</ul>

<h2 id="performance">性能劣化处理</h2>
<p>性能指标监控：</p>
<ul>
<li>FCP (First Contentful Paint) > 2秒</li>
<li>LCP (Largest Contentful Paint) > 3秒</li>
<li>FID (First Input Delay) > 100ms</li>
</ul>
"""
    },
    {
        "id": "sop-004",
        "title": "SRE On-Call SOP",
        "department": "SRE",
        "tags": ["K8s集群", "监控告警", "容量规划", "故障响应"],
        "content": """
<h1>SRE On-Call SOP</h1>

<h2 id="k8s-issue">K8s 集群问题</h2>
<p>常见问题：</p>
<ul>
<li>Pod无法调度</li>
<li>节点NotReady</li>
<li>服务发现异常</li>
<li>Ingress流量异常</li>
</ul>
<p>排查步骤：</p>
<ol>
<li>检查节点状态和资源使用</li>
<li>检查Pod事件日志</li>
<li>检查网络策略和Service配置</li>
<li>必要时重启问题组件</li>
</ol>

<h2 id="monitoring">监控告警处理</h2>
<p>告警分级响应：</p>
<table>
<tr><th>级别</th><th>处理时间</th><th>示例</th></tr>
<tr><td>Critical</td><td>5分钟</td><td>服务完全不可用</td></tr>
<tr><td>Warning</td><td>30分钟</td><td>资源使用超80%</td></tr>
<tr><td>Info</td><td>工作时间</td><td>非关键指标波动</td></tr>
</table>

<h2 id="capacity">容量规划</h2>
<p>容量评估指标：</p>
<ul>
<li>CPU使用率</li>
<li>内存使用率</li>
<li>网络带宽</li>
<li>存储容量</li>
</ul>
<p>扩容触发条件：任一指标持续超过70%</p>

<h2 id="incident">故障响应流程</h2>
<ol>
<li>确认故障现象和影响范围</li>
<li>拉起故障响应群，通知相关人员</li>
<li>定位故障原因</li>
<li>执行修复或回滚</li>
<li>验证恢复并通知</li>
<li>编写故障报告</li>
</ol>
"""
    },
    {
        "id": "sop-005",
        "title": "安全团队 On-Call SOP",
        "department": "安全团队",
        "tags": ["安全事件分级", "入侵检测", "漏洞响应"],
        "content": """
<h1>安全团队 On-Call SOP</h1>

<h2 id="security-level">安全事件分级</h2>
<table>
<tr><th>级别</th><th>定义</th><th>示例</th></tr>
<tr><td>P0</td><td>数据泄露、系统被入侵</td><td>用户数据外泄、挖矿木马</td></tr>
<tr><td>P1</td><td>高危漏洞被利用</td><td>SQL注入、RCE漏洞</td></tr>
<tr><td>P2</td><td>中危漏洞、可疑行为</td><td>暴力破解尝试、异常登录</td></tr>
<tr><td>P3</td><td>低危漏洞、安全建议</td><td>信息泄露、配置不当</td></tr>
</table>

<h2 id="intrusion">入侵检测响应</h2>
<p>入侵告警处理：</p>
<ol>
<li>确认告警真实性，排除误报</li>
<li>隔离受影响系统</li>
<li>收集证据（日志、快照）</li>
<li>分析入侵路径和影响范围</li>
<li>清除威胁并修复漏洞</li>
<li>加固防护措施</li>
<li>编写安全事件报告</li>
</ol>

<h2 id="vulnerability">漏洞响应流程</h2>
<p>漏洞处理时效要求：</p>
<ul>
<li>高危漏洞：24小时内修复或缓解</li>
<li>中危漏洞：7天内修复</li>
<li>低危漏洞：下个版本迭代修复</li>
</ul>
<p>修复步骤：</p>
<ol>
<li>评估漏洞影响和利用难度</li>
<li>制定修复方案</li>
<li>测试环境验证</li>
<li>生产环境修复</li>
<li>验证修复效果</li>
</ol>
"""
    },
    {
        "id": "sop-006",
        "title": "数据平台 On-Call SOP",
        "department": "数据平台",
        "tags": ["数据管道故障", "ETL失败", "Spark集群"],
        "content": """
<h1>数据平台 On-Call SOP</h1>

<h2 id="pipeline">数据管道故障</h2>
<p>数据管道常见问题：</p>
<ul>
<li>数据延迟超过阈值</li>
<li>数据丢失或重复</li>
<li>数据格式异常</li>
</ul>
<p>处理步骤：</p>
<ol>
<li>确认故障管道和影响的数据表</li>
<li>检查上游数据源是否正常</li>
<li>检查管道任务状态</li>
<li>必要时重新触发任务</li>
<li>验证数据完整性</li>
</ol>

<h2 id="etl">ETL 失败处理</h2>
<p>ETL任务失败排查：</p>
<ol>
<li>查看任务日志定位错误原因</li>
<li>检查源数据是否有异常</li>
<li>检查目标表是否有锁或空间不足</li>
<li>修复问题后重跑任务</li>
<li>验证数据准确性</li>
</ol>

<h2 id="spark">Spark 集群问题</h2>
<p>Spark任务异常：</p>
<ul>
<li>Executor丢失</li>
<li>内存不足</li>
<li>shuffle失败</li>
</ul>
<p>处理：</p>
<ol>
<li>调整executor内存配置</li>
<li>优化数据倾斜问题</li>
<li>增加重试次数</li>
</ol>
"""
    },
    {
        "id": "sop-007",
        "title": "移动端 On-Call SOP",
        "department": "移动端",
        "tags": ["App崩溃率", "热修复", "推送服务"],
        "content": """
<h1>移动端 On-Call SOP</h1>

<h2 id="crash">App 崩溃率处理</h2>
<p>崩溃率告警阈值：日活用户崩溃率 > 0.5%</p>
<p>处理步骤：</p>
<ol>
<li>查看崩溃堆栈，确认崩溃类型</li>
<li>分析影响范围（系统版本、设备型号）</li>
<li>检查最近发版是否有相关变更</li>
<li>评估是否需要紧急热修复</li>
<li>发布修复版本</li>
</ol>

<h2 id="hotfix">热修复流程</h2>
<p>热修复适用场景：</p>
<ul>
<li>紧急功能bug</li>
<li>安全漏洞修复</li>
<li>合规问题修复</li>
</ul>
<p>热修复发布流程：</p>
<ol>
<li>开发修复补丁</li>
<li>测试验证</li>
<li>灰度发布（10% → 50% → 100%）</li>
<li>监控崩溃率变化</li>
</ol>

<h2 id="push">推送服务异常</h2>
<p>推送问题排查：</p>
<ol>
<li>检查推送服务状态</li>
<li>确认推送通道（APNs/FCM/厂商通道）</li>
<li>检查推送证书是否过期</li>
<li>查看推送日志确认送达情况</li>
</ol>
"""
    },
    {
        "id": "sop-008",
        "title": "AI & 算法 On-Call SOP",
        "department": "AI & 算法",
        "tags": ["模型推理延迟", "推荐质量下降", "GPU集群"],
        "content": """
<h1>AI & 算法 On-Call SOP</h1>

<h2 id="inference">模型推理延迟</h2>
<p>推理延迟告警阈值：P99 > 500ms</p>
<p>排查步骤：</p>
<ol>
<li>检查模型服务实例状态</li>
<li>检查GPU使用率和显存</li>
<li>检查请求队列积压情况</li>
<li>分析是否有异常输入（超长文本）</li>
</ol>
<p>缓解措施：</p>
<ul>
<li>扩容推理服务实例</li>
<li>启用模型量化</li>
<li>调整batch size</li>
</ul>

<h2 id="recommendation">推荐质量下降</h2>
<p>推荐效果监控指标：</p>
<ul>
<li>CTR下降超过10%</li>
<li>转化率异常波动</li>
<li>用户反馈增加</li>
</ul>
<p>排查：</p>
<ol>
<li>检查特征数据是否正常</li>
<li>检查模型版本是否变更</li>
<li>检查A/B实验配置</li>
<li>分析bad case</li>
</ol>

<h2 id="gpu">GPU 集群问题</h2>
<p>GPU故障处理：</p>
<ol>
<li>检查GPU健康状态（nvidia-smi）</li>
<li>检查CUDA版本兼容性</li>
<li>检查训练任务状态</li>
<li>必要时迁移任务到健康节点</li>
</ol>
"""
    },
    {
        "id": "sop-009",
        "title": "QA On-Call SOP",
        "department": "QA",
        "tags": ["测试环境故障", "自动化测试", "发版卡点"],
        "content": """
<h1>QA On-Call SOP</h1>

<h2 id="test-env">测试环境故障</h2>
<p>测试环境常见问题：</p>
<ul>
<li>环境不可用</li>
<li>数据被污染</li>
<li>配置错误</li>
</ul>
<p>处理步骤：</p>
<ol>
<li>确认影响范围和阻塞的开发人员</li>
<li>检查基础服务状态</li>
<li>必要时重建环境</li>
<li>恢复测试数据</li>
<li>通知开发恢复</li>
</ol>

<h2 id="automation">自动化测试失败</h2>
<p>自动化测试失败分类：</p>
<ul>
<li>代码问题（真实bug）</li>
<li>环境问题（不稳定）</li>
<li>用例问题（需要更新）</li>
</ul>
<p>处理：</p>
<ol>
<li>分析失败原因</li>
<li>区分是产品bug还是用例问题</li>
<li>产品bug：提交bug单</li>
<li>用例问题：更新用例</li>
</ol>

<h2 id="release">发版卡点</h2>
<p>发版前检查清单：</p>
<ul>
<li>所有P0/P1 bug已修复验证</li>
<li>自动化测试通过率达标</li>
<li>性能测试通过</li>
<li>安全扫描无高危问题</li>
</ul>
"""
    },
    {
        "id": "sop-010",
        "title": "网络 & CDN On-Call SOP",
        "department": "网络 & CDN",
        "tags": ["CDN节点故障", "DNS异常", "DDoS防护"],
        "content": """
<h1>网络 & CDN On-Call SOP</h1>

<h2 id="cdn-node">CDN 节点故障</h2>
<p>CDN故障现象：</p>
<ul>
<li>资源加载失败</li>
<li>响应延迟升高</li>
<li>部分地区无法访问</li>
</ul>
<p>处理：</p>
<ol>
<li>确认故障节点范围</li>
<li>切换到备用节点或供应商</li>
<li>联系CDN服务商</li>
<li>验证流量切换效果</li>
</ol>

<h2 id="dns">DNS 异常处理</h2>
<p>DNS问题排查：</p>
<ol>
<li>确认DNS解析是否正确</li>
<li>检查DNS配置记录</li>
<li>检查DNS服务器状态</li>
<li>必要时调整TTL加速生效</li>
</ol>

<h2 id="ddos">DDoS 防护</h2>
<p>DDoS攻击告警：</p>
<ol>
<li>确认攻击类型和规模</li>
<li>启用高防IP或WAF</li>
<li>配置限速策略</li>
<li>联系运营商协助</li>
<li>攻击结束后分析并加固</li>
</ol>
<p>日常防护措施：</p>
<ul>
<li>配置WAF规则</li>
<li>设置访问频率限制</li>
<li>启用验证码挑战</li>
</ul>
"""
    }
]


def generate_html_files():
    """生成HTML文件到data/raw目录"""
    DATA_RAW.mkdir(parents=True, exist_ok=True)

    for doc in SOP_DOCUMENTS:
        # 包装为完整HTML
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{doc['title']}</title>
</head>
<body>
{doc['content']}
<script>
// 统计脚本 - replication相关配置
var _stats = {{ replication: true, source: 'cdn-primary' }};
</script>
</body>
</html>"""

        file_path = DATA_RAW / f"{doc['id']}.html"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"生成: {file_path}")

    # 生成metadata.json
    metadata = []
    for doc in SOP_DOCUMENTS:
        metadata.append({
            "id": doc["id"],
            "title": doc["title"],
            "department": doc["department"],
            "tags": doc["tags"]
        })

    metadata_path = DATA_RAW / "metadata.json"
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"生成: {metadata_path}")


if __name__ == "__main__":
    print("=== 生成SOP测试数据 ===")
    generate_html_files()
    print("\n完成！共生成10份SOP文档")
