PROMPT_TEMPLATES = {
    "CICC": 
    [{"type": "text", 
      "text": """
      Please extract the 'Ledger Balance' and corresponding currency type 'CCY' from the 'Cash Balance for' section in this PDF document.
      The 'Cash Value' in this section corresponds to 'Total' in the output, with 'Total_type' being 'HKD'.
      Then, from the 'Securities Holding for' section, for each holding, extract the 'Sec.code', 'Holding C/F', 'Closing Price', and 'CCY'.
      
      IMPORTANT: For each holding, identify the price currency and output as 'PriceCurrency' field (values: USD/HKD/CNY).
      """}],

    "First Shanghai": 
    [{"type": "text", 
      "text": """
      Please extract the 'Ledger Balance Original Currency' and corresponding currency type 'Currency' from the 'Cash Holding' section in this PDF document.
      Then, from the 'Securities Holding' section, for each stock, extract the 'Stock Code', 'Month End Ledger Balance', and 'Closing Price'. The currency for each stock should be identified from its market group header (e.g., the currency is 'USD' for stocks under the 'US Market - USD' heading).
      If 'No Securities Holding' is written under a market group, it means there are no positions for that market.
      
      IMPORTANT: For each holding, identify the price currency and output as 'PriceCurrency' field (values: USD/HKD/CNY).
      """}],

    "HTI": 
    [{"type": "text", 
      "text": """
      Please extract the 'Balance C/F' and its corresponding 'Currency' from the 'Balance Summary' table in this PDF document. 'Total HKD Eqv.' in this table should be treated as 'Total'.
      Then, from the 'Equity Portfolio Summary' section, for each stock, extract the following: 'Sellable Quantity', 'Closing Price', and the 'StockCode'. Both the 'StockCode' and its 'Currency' can be found in the 'Market / Description' column (the currency is indicated within parentheses, like '(HKD)').
      
      IMPORTANT: For each holding, identify the price currency and output as 'PriceCurrency' field (values: USD/HKD/CNY).
      """}],

    "HUATAI": 
    [{"type": "text", 
      "text": """
      Please read the Cash section in the 'Portfolio Summary' table in this PDF document, extract the 'Net Balance' section and corresponding currency type.
      Then, from the 'Stock/Product Position' section, for each stock, extract the 'Code', 'Net Balance', and 'Closing Price'. The currency for each stock should be identified from its market group header row above it (e.g., extract 'USD' from the 'US - U.S. STOCK (USD)' row).
      
      IMPORTANT: For each holding, identify the price currency and output as 'PriceCurrency' field (values: USD/HKD/CNY).
      """}],

    "IB": 
    [{"type": "text", 
      "text": """
      In the 'Cash Report' section, which may span multiple pages:
        1. Find the block of rows under the 'HKD' header. Within this block, find the row labeled 'Ending Cash' and extract its value from the 'Total' column as the output for 'HKD'.
        2. Find the block of rows under the 'USD' header. Within this block, find the row labeled 'Ending Cash' and extract its value from the 'Total' column as the output for 'USD'.
        3. Do not confuse 'Ending Cash' with 'Starting Cash' or 'Ending Settled Cash'.
        Set 'CNY', 'Total', and 'Total_type' in the output to None.
      Then, from the 'Open Positions' section, for each position, extract the 'Symbol', 'Quantity', 'Mult' (as 'Multiplier'), and 'Close Price'. The currency for each position is determined by the currency header row (e.g., 'USD' or 'HKD') that appears above that group of positions.
      
      For Symbol field:
      - US options: use OCC format TICKER+YYMMDD+C/P+STRIKE*1000 (e.g., "SBET260116P41000")
      
      IMPORTANT: For each holding, identify the price currency and output as 'PriceCurrency' field (values: USD/HKD/CNY).
      """}],

    "LB": 
    [{"type": "text", 
      "text": """
      Please extract the 'Closing Balance' values from the 'Balance Details' section in this PDF document:
      - For the 'HKD' row, extract the 'Closing Balance' as output 'HKD'.
      - For the 'USD' row, extract the 'Closing Balance' as output 'USD'.
      - For the 'Total (HKD)' row, extract the 'Closing Balance (HKD)' as output 'Total'.
      Set 'CNY' to None and 'Total_type' to 'HKD'.
      Then, from the 'Portfolio Details' section, considering both 'Stock' and 'Option' categories, for each holding, extract the stock symbol (from the 'Description' column), 'Closing Qty', and 'Price'. The currency for each category is indicated in the category header (e.g., extract 'USD' from 'Stock (US; USD)').
      
      For stock symbol field:
      - US options: use OCC format TICKER+YYMMDD+C/P+STRIKE*1000 (e.g., "SBET260116P41000")
      
      IMPORTANT: For each holding, identify the price currency and output as 'PriceCurrency' field (values: USD/HKD/CNY).
      """}],

    "MOOMOO": 
    [{"type": "text", 
      "text": """
      Please extract the 'Ending Cash' from the 'USD', 'HKD' and 'CNH' tables in the 'Changes in Cash' section of this PDF document,
      as the output 'USD', 'HKD' and 'CNY' respectively. Set 'Total' and 'Total_type' in the output to None.
      
      Then, from the 'Ending Positions' section, extract data from BOTH tables:
      
      1. From the 'Securities' table, for each item extract:
         - 'Symbol' column → 'StockCode'
           * For stocks with format "Company Name TICKER": extract ONLY ticker (e.g., "Robinhood HOOD" → "HOOD")
           * For options: use OCC format TICKER+YYMMDD+C/P+STRIKE*1000 (e.g., "SBET260116P41000")
         - 'Symbol' column → 'Description' (same as Symbol)
         - 'Quantity' column → 'Holding'
         - 'Closing Price' column → 'Price'
         - 'Currency' column → 'PriceCurrency'
      
      2. From the 'Funds' table, for each item extract:
         - 'Symbol' column → 'StockCode' (extract ONLY the code at the end)
         - 'Symbol' column → 'Description' (extract the FULL text)
         - 'Quantity' column → 'Holding'
         - 'Closing Price' column → 'Price'
         - 'Currency' column → 'PriceCurrency'
      
      Note: The 'Funds' table's Symbol column contains both the fund name and code together.
      Consider table pagination.
      """}],

    "SDICS": 
    [{"type": "text", 
      "text": """
      Please extract the 'LEDGER BALANCE' corresponding to 'HKD', 'USD' and 'HKD EQD' from the 'Account Summary' table in this PDF document,
      as the output 'HKD', 'USD' and 'Total' respectively.
      Then, from the 'Equities Asset Summary' section, for each stock, extract the 'Code', 'CLOSING BAL' (Closing Balance), 'CLOSING PRICE', and 'CCY' (Currency).
      
      IMPORTANT: For each holding, identify the price currency and output as 'PriceCurrency' field (values: USD/HKD/CNY).
      """}],

    "TFI": 
    [{"type": "text", 
      "text": """
      Please extract the 'Ledger Balance' section and corresponding currency type 'Currency' from the 'Daily Account Balance' table in this PDF document.
      Then, from the '證券組合(Securities Position/Portfolio Holding)' section, for each stock, extract the stock code from "股票代號及名稱 Stock Code & Name", quantity from '結存股數 Closing Qty', and price from '收市價 Closing Price'. The currency for each stock should be identified from its market group header (e.g., the currency is 'HKD' for stocks under 'HK-HKD:', and 'USD' for stocks under 'USA-USD:').
      
      IMPORTANT: For each holding, identify the price currency and output as 'PriceCurrency' field (values: USD/HKD/CNY).
      """}],

    "TIGER": 
    [{"type": "text", 
      "text": """
      Please extract the 'Total' values corresponding to 'Ending Cash' from the 'Currency: USD' and 'Currency: HKD' tables in this PDF document,
      as the output 'USD' and 'HKD' respectively. Set 'Total' and 'Total_type' in the output to None.
      Then, from the 'Holdings' section, for each holding (including both 'Stock' and 'Option'), extract the 'Symbol' (as 'Stock Code'), 'Quantity' (as 'Holding'), 'Close Price', 'Currency', and 'Multiplier' (if visible in the table, extract the exact number; if not visible, set to null).
      
      For Symbol field:
      - US options: convert to OCC format TICKER+YYMMDD+C/P+STRIKE*1000 (e.g., "SBET 20260116 PUT 41.0" → "SBET260116P41000")
      - HK options: keep original format with 3-letter HKATS code (e.g., "CLI 260629 20.00 CALL")
      
      IMPORTANT: For each holding, identify the price currency and output as 'PriceCurrency' field (values: USD/HKD/CNY).
      """}]
}