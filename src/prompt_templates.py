PROMPT_TEMPLATES = {
    "CICC": 
    [{"type": "text", 
      "text": """
      Please extract the 'Ledger Balance' and corresponding currency type 'CCY' from the 'Cash Balance for' section in these screenshots.
      The 'Cash Value' in this section corresponds to 'Total' in the output, with 'Total_type' being 'HKD'.
      Then extract the 'Sec.code' and corresponding 'Holding C/F' from the 'Security Holding for' section.
      """}],

    "First Shanghai": 
    [{"type": "text", 
      "text": """
      Please extract the 'Ledger Balance Original Currency' and corresponding currency type 'Currency' from the 'Cash Holding' section in these screenshots.
      Then extract the 'Stock Code' and corresponding 'Month End Ledger Balance' from the 'Securities Holding' section.
      'No Securities Holding' means no positions, return None directly.
      """}],

    "HTI": 
    [{"type": "text", 
      "text": """
      Please extract the 'Balance C/F' corresponding to 'Currency' from the 'Balance Summary' table in these screenshots.
      'Total HKD Eqv.' represents 'Total'.
      Then extract the StockCode and corresponding 'Sellable Quantity' from the 'Equity Portfolio Summary' section.
      """}],

    "HUATAI": 
    [{"type": "text", 
      "text": """
      Please read the Cash section in the 'Portfolio Summary' table in these screenshots, extract the 'Net Balance' section and corresponding currency type.
      Then extract the 'Code' and corresponding 'Net Balance' from the 'Stock/Product Position' section.
      """}],

    "IB": 
    [{"type": "text", 
      "text": """
      Please read the 'Cash Report' section in these screenshots, considering table pagination.
      Extract the 'Total' corresponding to 'Ending Cash' for 'HKD' and 'USD' as the output 'HKD' and 'USD'.
      Note the distinction between 'Ending Cash' and 'Starting Cash', do not mistake 'Starting Cash' for 'Ending Cash'.
      Set 'CNY', 'Total' and 'Total_type' in the output to None.
      Then extract the 'Quantity' and corresponding 'Symbol' from the 'Open Positions' section.
      """}],

    "LB": 
    [{"type": "text", 
      "text": """
      Please extract the 'Closing Balance' values from the 'Balance Details' section in these screenshots:
      - For 'HKD' row, extract the 'Closing Balance' as output 'HKD'
      - For 'USD' row, extract the 'Closing Balance' as output 'USD'  
      - For 'Total (HKD)' row, extract the 'Closing Balance (HKD)' as output 'Total'
      Set 'CNY' to None and 'Total_type' to 'HKD'.
      Then extract the 'Closing Qty' and corresponding stock symbols from the 'Portfolio Details' section,
      considering both 'Stock' and 'Option' categories.
      """}],

    "MOOMOO": 
    [{"type": "text", 
      "text": """
      Please extract the 'Ending Cash' from the 'USD', 'HKD' and 'CNH' tables in the 'Changes in Cash' section of these screenshots,
      as the output 'USD', 'HKD' and 'CNY' respectively. Set 'Total' and 'Total_type' in the output to None.
      Then extract the 'Symbol' and corresponding 'Quantity' from the 'Ending Positions' section,
      as the output 'StockCode' and 'Holding' respectively.
      Consider table pagination.
      """}],

    "SDICS": 
    [{"type": "text", 
      "text": """
      Please extract the 'LEDGER BALANCE' corresponding to 'HKD', 'USD' and 'HKD EQD' from the 'Account Summary' table in these screenshots,
      as the output 'HKD', 'USD' and 'Total' respectively.
      Then extract the 'Code' and corresponding 'CLOSING BAL' from the 'Equities Asset Summary' section.
      """}],

    "TFI": 
    [{"type": "text", 
      "text": """
      Please extract the 'Ledger Balance' section and corresponding currency type 'Currency' from the 'Daily Account Balance' table in these screenshots.
      Then extract the 'Stock Code' and corresponding 'Closing Qty' from the 'Securities Position/Portfolio Holding' section.
      """}],

    "TIGER": 
    [{"type": "text", 
      "text": """
      Please extract the 'Total' values corresponding to 'Ending Cash' from the 'Currency：USD' and 'Currency：HKD' tables in these screenshots,
      as the output 'USD' and 'HKD' respectively. Set 'Total' and 'Total_type' in the output to None.
      Then extract the 'Symbol' and corresponding 'Quantity' from the 'Holdings' section,
      as the output 'Stock Code' and 'Holding' respectively.
      """}]
}