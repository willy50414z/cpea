# 相同索引版第二次測試

使用者授權再跑一次。已核對題目、完整messages、prompt/schema/catalog/source指紋，以及DeepSeek-V4.1-Flash、seed42、temperature1、top_p1皆與EXP-012相同；沒有調整索引規則、補end或覆寫第一次結果。

**本次完整涵蓋目標詞5/7，上次2/7；保留母體改為正確的population。盤點日期與月份仍各少一字，未符合預定的全數完整片段標準。** 這是第一步的片段品質判讀，不等於整題業務答案錯誤率；第二／三步未執行。

| 需求 | 本次Python裁切 | 片段判讀 |
|---|---|---|
| 庫存件數 | 對照各店各商品的盤點庫存件數 | 完整，包含較長但相關的店商品脈絡 |
| 盤點日期 | 庫存盤點日 | 缺「期」 |
| 月份 | `2026 年 9 ` | 缺「月」 |
| 通路 | 線上通路 | 完整 |
| 折扣金額 | 折扣金額 | 完整 |
| 淨銷售額 | 淨銷售額 | 完整 |
| 保留母體 | 保留所有庫存商品 | 完整，kind=population |

精確等於最短目標詞範圍的是4/7；庫存件數採較長合理片段，完整覆蓋因此為5/7。前次完整覆蓋與最短精確範圍皆2/7，不能把兩種指標混稱為同一分數。盤點日期列attribute且無庫存日期filter；銷售兩度量綁定九月與online。key／grain仍未獨立列項，因此不宣稱需求完整性或來源映射已通過。

實際1次provider呼叫，input6707／output1018 tokens，約14.20秒，Azure美元價格未知。相同單次硬上限：最多30000input／4096output、context32768、safety1024、timeout300秒／wall900秒、SDK retries=0。沒有第三次或自動修正；原始raw、parsed indices與Python衍生結果分開保存。

- [首次呼叫證據](../evidence/EV-20261021T034825-0e02c9b4.json)：source unchanged，第一步索引結構PASS。
- [Fresh replay](../evidence/EV-20261021T035012-bc6c0422.json)：1筆raw及parsed／衍生結果一致，無新provider呼叫。
- [機器比較資料](indexed-recall-repeat-results.json)、[上次結果](indexed-recall-results.md)。新raw：Task `.local/three-stage-20261021T034827Z-e0692c/`。
- 程式未變，沿用同指紋下先前156回歸，不重跑整套單元測試。本次語意核對仍由主agent執行，沒有新增獨立oracle核准。

流程偏差：前置核對誤用系統Python而失敗，shell未停止，已授權的單次runner先啟動；EXP-013與狀態是啟動後補登，不能宣稱新EXP事前建立。runner既有單次預算仍生效，已用專案.venv補核對相同輸入／版本／設定，沒有額外模型重跑。

本次完整片段標準仍未達，固定候選結果不因重跑而改成PASS。兩次結果全部保留；不據單次改善推論準確率或可靠性，不擴第二步、六題、完整Gate或Ollama。
