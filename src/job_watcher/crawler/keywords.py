from __future__ import annotations


TARGET_2027_KEYWORDS = [
    "2027届",
    "2027 届",
    "27届",
    "2027年应届",
    "2027毕业",
]

CAMPUS_RECRUITMENT_KEYWORDS = [
    "校园招聘",
    "秋招",
    "秋季招聘",
    "校招",
    "应届生",
    "管培生",
    "招聘简章",
]

RECRUITMENT_CONTEXT_KEYWORDS = [
    "网申",
    "宣讲会",
    "双选会",
    "笔试",
    "面试",
    "测评",
    "投递",
    "简历",
    "截止时间",
]

RECRUITMENT_KEYWORDS = TARGET_2027_KEYWORDS + CAMPUS_RECRUITMENT_KEYWORDS + RECRUITMENT_CONTEXT_KEYWORDS

SECURITY_KEYWORDS = [
    "网络安全",
    "信息安全",
    "数据安全",
    "等保",
    "渗透测试",
    "安全运营",
    "SOC",
    "应急响应",
    "漏洞",
    "攻防",
    "密码",
    "商用密码",
    "信创安全",
]

COMPUTER_KEYWORDS = [
    "软件开发",
    "后端",
    "Java",
    "Python",
    "C++",
    "前端",
    "算法",
    "数据分析",
    "大数据",
    "云计算",
    "运维",
    "系统工程师",
    "数据库",
    "IT",
    "信息技术",
    "数字化",
    "信息化",
    "网络管理",
]


def matched_keywords(text: str, keywords: list[str]) -> list[str]:
    lower_text = text.lower()
    return [keyword for keyword in keywords if keyword.lower() in lower_text]
