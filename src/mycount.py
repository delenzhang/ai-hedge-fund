class CountInfo:
  initial_cash = 1500
  margin_requirement = 0.5

# 可选：为每个股票设置不同的初始持仓
# 如果不需要初始持仓，可以设置为空字典 {}，所有股票将使用默认值（0）
initial_positions = {
        # 示例：为不同股票设置不同的初始持仓
        "PYPL": {
            "long": 60,
            "long_cost_basis": 67,
            "short": 0,
            "short_cost_basis": 0.0,
        },
        "BABA": {
            "long": 61,
            "long_cost_basis": 163.6,
            "short": 0,
            "short_cost_basis": 0.0,
        },
        "NUS": {
            "long": 540,
            "long_cost_basis": 14,
            "short": 0,
            "short_cost_basis": 0.0,
        },
        "NIO": {
            "long": 150,
            "long_cost_basis": -8.5,
            "short": 0,
            "short_cost_basis": 0.0,
        },
        "MP": {
            "long": 55,
            "long_cost_basis": 70,
            "short": 0,
            "short_cost_basis": 0.0,
        },
    }
    
    # 可选：为每个股票设置不同的初始已实现收益
    # 如果不需要初始已实现收益，可以设置为空字典 {}，所有股票将使用默认值（0.0）
initial_realized_gains = {
        # 示例：为不同股票设置不同的初始已实现收益
        "PYPL": {
            "long": -42.6,
            "short": 0.0,
        },
        "BABA": {
            "long": -132.9,
            "short": 0.0,
        },
        "NUS": {
             "long": -2102,
            "short": 0.0,
        },
        "NIO": {
            "long": 2232,
            "short": 0.0,
        },
        "MP": {
            "long": -764,
            "short": 0.0,
        }
    }
