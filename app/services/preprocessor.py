# 数据预处理服务：HTML解析 + jieba分词

import re

import jieba
from bs4 import BeautifulSoup

from app.config import get_settings

settings = get_settings()


class ProcessedDocument:
    """预处理后的文档结构"""

    def __init__(
        self,
        doc_id: str,
        title: str,
        content: str,
        content_raw: str,
        department: str,
        tags: list[str],
        sections: list[dict],
    ):
        self.id = doc_id
        self.title = title
        self.content = content  # 分词后的内容
        self.content_raw = content_raw  # 原始文本
        self.department = department
        self.tags = tags
        self.sections = sections


class DocumentPreprocessor:
    """文档预处理器"""

    def __init__(self):
        # 初始化jieba分词（加载自定义词典可在此扩展）
        self._init_jieba()

    def _init_jieba(self):
        """初始化jieba分词器"""
        # 添加技术领域常用词
        tech_words = [
            "OOM",
            "QPS",
            "TPS",
            "API",
            "SDK",
            "CPU",
            "GPU",
            "内存",
            "主从延迟",
            "慢查询",
            "连接池",
            "热修复",
            "灰度发布",
            "容器化",
            "K8s",
            "Kubernetes",
            "微服务",
            "分布式",
            "ETL",
            "OLAP",
            "OLTP",
            "SQL",
            "NoSQL",
            "CDN",
            "DNS",
            "DDoS",
            "WAF",
            "FCP",
            "LCP",
            "埋点",
            "召回",
            "推荐",
            "特征",
        ]
        for word in tech_words:
            jieba.add_word(word, freq=1000)

    def parse_html(self, html_content: str, doc_id: str) -> ProcessedDocument:
        """
        解析HTML文档

        Args:
            html_content: HTML原文
            doc_id: 文档ID

        Returns:
            ProcessedDocument: 预处理后的文档
        """
        soup = BeautifulSoup(html_content, "lxml")

        # 移除script和style标签
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        # 提取标题
        title = self._extract_title(soup)

        # 提取正文并按章节拆分
        sections = self._extract_sections(soup)

        # 合并正文
        content_raw = self._merge_sections(sections)

        # jieba分词
        content_tokenized = self._tokenize(content_raw)

        # 从metadata提取部门信息（或从内容推断）
        department = self._extract_department(doc_id, title)

        # 提取标签
        tags = self._extract_tags(soup, content_raw)

        return ProcessedDocument(
            doc_id=doc_id,
            title=title,
            content=content_tokenized,
            content_raw=content_raw,
            department=department,
            tags=tags,
            sections=sections,
        )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """提取文档标题"""
        # 优先h1
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        # 其次title标签
        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text(strip=True)

        return "未知标题"

    def _extract_sections(self, soup: BeautifulSoup) -> list[dict]:
        """提取章节结构

        支持两种 HTML 布局：
          1. <body> 下直接放 <h2>/<p>（早期模板）
          2. <body><header><h1></header><main><h2><h3><p></main></body>（官方模板）
        统一用 find_all 扁平化遍历所有 h2/h3/p/ul/ol/table/pre 元素。
        """
        sections = []
        current_section = None

        body = soup.find("body")
        if not body:
            return sections

        # 扁平化按文档顺序遍历所有标题与内容元素
        for element in body.find_all(["h1", "h2", "h3", "p", "ul", "ol", "table", "pre"]):
            name = element.name
            if name == "h1":
                # 主标题：跳过（由 _extract_title 单独处理）
                continue
            if name in ("h2", "h3"):
                # h2 = 主章节；h3 = 子场景。都视为新 section，让正文跟在最近的标题后。
                if current_section:
                    sections.append(current_section)
                current_section = {
                    "heading": element.get_text(strip=True),
                    "anchor": element.get("id", ""),
                    "content": "",
                    "level": name,
                }
            else:
                # 正文内容
                text = element.get_text(strip=True, separator=" ")
                if not text:
                    continue
                if current_section:
                    current_section["content"] += text + "\n"
                else:
                    current_section = {
                        "heading": "概述",
                        "anchor": "",
                        "content": text + "\n",
                        "level": "",
                    }

        if current_section:
            sections.append(current_section)

        return sections

    def _merge_sections(self, sections: list[dict]) -> str:
        """合并章节内容"""
        parts = []
        for section in sections:
            heading = section.get("heading", "")
            content = section.get("content", "")
            if heading:
                parts.append(f"【{heading}】\n{content}")
            else:
                parts.append(content)
        return "\n".join(parts)

    def _tokenize(self, text: str) -> str:
        """jieba分词，返回空格分隔的词序列"""
        # 清理多余空白
        text = re.sub(r"\s+", " ", text)
        # 分词
        words = jieba.cut(text)
        # 过滤单字和标点
        words = [w for w in words if len(w) > 1 or w.isalnum()]
        return " ".join(words)

    def _extract_department(self, doc_id: str, title: str = "") -> str:
        """从 title 或 doc_id 推断部门

        优先用 title（取 "XX On-Call" 之前的部分作为部门名）；
        失败回退到 doc_id 硬映射，对新版 HTML 标题里有附加描述（"& 故障处理指南" 等）也兼容。
        """
        if title:
            # 移除 HTML 实体已经在 BeautifulSoup 阶段处理
            # 切 "On-Call" / "On Call" / "OnCall" 前缀
            import re

            m = re.split(r"\s*On[\s\-]?Call", title, maxsplit=1, flags=re.IGNORECASE)
            if m and m[0].strip():
                return m[0].strip()

        department_map = {
            "sop-001": "后端服务",
            "sop-002": "数据库DBA",
            "sop-003": "前端",
            "sop-004": "SRE",
            "sop-005": "信息安全",
            "sop-006": "数据平台",
            "sop-007": "移动客户端",
            "sop-008": "AI算法",
            "sop-009": "QA",
            "sop-010": "网络与CDN",
        }
        return department_map.get(doc_id, "未知部门")

    def _extract_tags(self, soup: BeautifulSoup, content: str) -> list[str]:
        """提取标签"""
        tags = []

        # 从meta标签提取（如有）
        meta_keywords = soup.find("meta", attrs={"name": "keywords"})
        if meta_keywords and meta_keywords.get("content"):
            tags.extend(meta_keywords["content"].split(","))

        # 简单的关键词提取（实际可用TF-IDF或NER）
        keywords = [
            "OOM",
            "主从延迟",
            "慢查询",
            "白屏",
            "CDN",
            "K8s",
            "入侵",
            "ETL",
            "崩溃",
            "推理延迟",
            "DDoS",
            "DNS",
            "热修复",
        ]
        for kw in keywords:
            if kw in content:
                tags.append(kw)

        return list(set(tags))


# 模块级单例
_preprocessor: DocumentPreprocessor | None = None


def get_preprocessor() -> DocumentPreprocessor:
    """获取预处理器单例"""
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = DocumentPreprocessor()
    return _preprocessor
