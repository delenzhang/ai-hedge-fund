class CountInfo:
  initial_cash = 1500
  margin_requirement = 0.5

# 可选：为每个股票设置不同的初始持仓
# 如果不需要初始持仓，可以设置为空字典 {}，所有股票将使用默认值（0）
initial_positions = {
        # 示例：为不同股票设置不同的初始持仓
        "PYPL": {
            "long": 70,
            "long_cost_basis": 72,
            "short": 0,
            "short_cost_basis": 0.0,
        },
        "BABA": {
            "long": 26,
            "long_cost_basis": 180.2,
            "short": 0,
            "short_cost_basis": 0.0,
        },
        "NUS": {
            "long": 200,
            "long_cost_basis": 22,
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
        "EL": {
           "long": 14,
            "long_cost_basis": 488,
            "short": 0,
            "short_cost_basis": 0.0, 
        },
        "INTC": {
           "long": 500,
           "long_cost_basis": 35,
            "short": 0,
            "short_cost_basis": 0.0, 
        },
        "ORCL": {
            "long": 12,
            "long_cost_basis": 240,
            "short": 0,
            "short_cost_basis": 0.0, 
        }
    }
    
    # 可选：为每个股票设置不同的初始已实现收益
    # 如果不需要初始已实现收益，可以设置为空字典 {}，所有股票将使用默认值（0.0）
initial_realized_gains = {
        # 示例：为不同股票设置不同的初始已实现收益
        "PYPL": {
            "long": -800,
            "short": 0.0,
        },
        "BABA": {
            "long": -708,
            "short": 0.0,
        },
        "NUS": {
             "long": -2214,
            "short": 0.0,
        },
        "NIO": {
            "long": 2232,
            "short": 0.0,
        },
        "MP": {
            "long": -764,
            "short": 0.0,
        },
        "EL": {
           "long": -5591,
            "short": 0.0,
        },
        "INTC": {
          "long": -555,
            "short": 0.0,
        },
        "ORCL": {
           "long": -220,
            "short": 0.0,
        }
    }
