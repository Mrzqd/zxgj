RENOVATION_STAGES = [
    {"value": "design", "label": "设计费"},
    {"value": "doors_windows", "label": "门窗"},
    {"value": "demolition", "label": "拆改"},
    {"value": "water_electricity", "label": "水电"},
    {"value": "masonry", "label": "瓦工"},
    {"value": "carpentry", "label": "木工"},
    {"value": "paint", "label": "油漆"},
    {"value": "kitchen_bath", "label": "厨卫"},
    {"value": "appliances", "label": "家电"},
    {"value": "furniture", "label": "家具"},
    {"value": "soft_decoration", "label": "软装"},
    {"value": "completion", "label": "竣工"},
    {"value": "other", "label": "其他"},
]

DEFAULT_PROJECT_STAGES = [
    {"value": "design", "label": "设计规划", "planned_days": 7},
    {"value": "demolition", "label": "拆改", "planned_days": 5},
    {"value": "water_electricity", "label": "水电", "planned_days": 7},
    {"value": "masonry", "label": "瓦工/泥木", "planned_days": 14},
    {"value": "carpentry", "label": "木工", "planned_days": 10},
    {"value": "paint", "label": "油漆", "planned_days": 10},
    {"value": "installation", "label": "安装", "planned_days": 7},
    {"value": "furniture", "label": "家具家电", "planned_days": 7},
    {"value": "completion", "label": "竣工验收", "planned_days": 3},
]

AMOUNT_CATEGORIES = [
    {"value": "full", "label": "全款"},
    {"value": "deposit", "label": "定金"},
    {"value": "progress", "label": "中期款"},
    {"value": "final", "label": "尾款"},
    {"value": "addition", "label": "增项"},
    {"value": "refund", "label": "退款"},
]

TASK_STATUSES = [
    {"value": "open", "label": "待处理"},
    {"value": "doing", "label": "处理中"},
    {"value": "done", "label": "已完成"},
]

INSPECTION_STATUSES = [
    {"value": "pending", "label": "待验收"},
    {"value": "pass", "label": "通过"},
    {"value": "fail", "label": "需整改"},
    {"value": "na", "label": "不适用"},
]
