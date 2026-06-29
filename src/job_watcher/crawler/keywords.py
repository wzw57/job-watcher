from __future__ import annotations


RECRUITMENT_KEYWORDS = [
    "2027届",
    "2027 届",
    "27届",
    "校园招聘",
    "秋招",
    "秋季招聘",
    "校招",
    "网申",
    "应届生",
    "管培生",
    "招聘简章",
    "宣讲会",
    "双选会",
    "笔试",
    "面试",
    "测评",
    "投递",
    "简历",
    "截止时间",
]

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
