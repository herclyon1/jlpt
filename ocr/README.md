# OCR 工具

macOS 自带 Vision 引擎，日语识别准确率高，**零 API 成本、纯离线**。支持 PDF 与图片（jpg/png/heic/tiff）。

## 单文件

```bash
./pdfocr "试卷.pdf" > 输出.txt       # 全本
./pdfocr "试卷.pdf" 8 12 > 输出.txt  # 只做第 8-12 页
./pdfocr "答案卡.jpg" > 输出.txt      # 图片
```

实测：36 页试卷 9.3 秒、45 页 5.2 万字全本一次跑完。

## 批处理

```bash
./batch.sh                     # 默认 ../exams/raw -> ../exams/ocr
./batch.sh 输入目录 输出目录
```

已处理过且源文件未更新的自动跳过。实测 10 个文件 58 秒全部成功。

## 全自动

**把 PDF/图片传到仓库的 `exams/raw/`，其余不用管。**

`auto.sh` 会：拉取仓库 → OCR 新文件 → 提交推回 `exams/ocr/`。

先手动跑一次确认正常：
```bash
bash ocr/auto.sh && tail -20 ocr/auto.log
```

装成每 10 分钟自动执行（这条命令会在你的账户下注册一个后台定时任务，请自行确认后执行）：
```bash
cp ocr/com.herclyon.jlpt-ocr.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.herclyon.jlpt-ocr.plist
```

查看日志：`tail -f ocr/auto.log`

随时停止并卸载：
```bash
launchctl unload ~/Library/LaunchAgents/com.herclyon.jlpt-ocr.plist && rm ~/Library/LaunchAgents/com.herclyon.jlpt-ocr.plist
```

## 已知识别偏差（转标准格式时留意）

- 选项编号 `1` 偶尔识成 `|` 或 `l`
- `N1` 有时识成 `NI`
- **双栏排版的选项按视觉行序输出（1→3→2→4），需按语义重排**
- 汉字异体按印刷原样输出，不做归一

重新编译：`swiftc -O -o pdfocr pdfocr.swift`
