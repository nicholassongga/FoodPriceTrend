# FoodPriceTrend

Food price fluctuations are of significant economic and social concern, especially for staple foods such as eggs. Early and accurate forecasts of price movements can benefit consumers, retailers, and policymakers. In this study, we investigated whether data from Google Trends, which measures the popularity of search terms over time, can be used as a predictive signal for egg price dynamics. Using a custom Python framework, we developed two complementary tools: (1) an automated script that evaluated the correlation between Google search frequencies of selected keywords and egg prices; and (2) an interactive web application that enables users to test keyword combinations in real time. Results suggest that online search behavior provides measurable signals that precede changes in egg prices, and thus Google Trends may serve as a low-cost and scalable forecasting instrument.

Click the URL: https://foodpricetrend.streamlit.app to view the live web app prototype demo.

## Installation

```
  pip3 install -r requirement.txt
```

## Run

(1) an automated script that evaluated the correlation between Google search frequencies of selected keywords and egg prices

```
  python3 compare_trend_price.py
```

(2) an interactive web application that enables users to test keyword combinations in real time

```  
  python3 -m streamlit run web_trend_price.py
```
