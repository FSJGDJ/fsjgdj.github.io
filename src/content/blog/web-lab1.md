---
title: 'Web 技术实验 1 完成指南：个人主页与图书售卖界面'
description: '整理《Web技术实验指导书》第三、四章实验 1 的完整落地指南：任务一多页面个人网站（外部样式表）、任务二图书售卖界面（内部样式表）、实验报告写法、提交检查清单与五个常见坑。'
pubDate: 2026-10-08
tags: ['Web技术', 'HTML', 'CSS', '实验报告']
---

> 本文是对《Web技术（双语）》实验 1 的完整落地指南，整理自实验指导书第三章、第四章与实验 1 安排文档。报告截止 **10 月 30 日**，提交地址为腾讯文档表单（<https://docs.qq.com/form/page/DTmNPdGF0cE9KbUVD>）。

## 写在前面：这份实验到底要做什么

Web 技术课的第一次课内实验，看着像"做一个网页"这样的大而泛的说法，实际上边界划得很死：**两个任务、两种样式表组织方式、一份两页左右的实验报告**。

任务一来自第三章的实验内容 1，做一个**个人主页/网站**——八项指定内容分布在多个 HTML 文件里，用**外部样式表**统一样式，页面之间靠超链接互相跳转。任务二来自第四章的实验内容 1，做一个**图书售卖界面**——所有内容塞进**单个 HTML 文件**，样式写在页面内部的 `<style>` 里。

这两道题几乎是同一份知识点的两次正面与反面演练：**多页面 + 外部 CSS** 考察的是结构和复用，单文件 + 内部 CSS 考察的是对样式作用域的理解。把这个差异想明白了，后面的写法就是水到渠成。

## 一、先把范围划清楚：哪些不用做

这是最容易翻车的地方。指导书里列了一堆实验内容，但本次只做其中一部分：

- 第三章的**实验内容 2**（用 JavaScript 求一元二次方程 ax²+bx+c=0 的根）**本次不要求**，只做实验内容 1。
- 第四章的**实验内容 2、3、4**（main.php 生成订单页、fwrite 写文件、reset 清空）**本次不要求**，只做实验内容 1 这个静态售卖界面。所以表单的 `action` 可以先空着或填 `#`，不需要任何后端处理。
- 指导书备注了几条硬性要求：**代码要求手工输入**，不要用工具自动生成；字体颜色样式自己决定；多个页面之间必须能相互链接访问。

把"不做"的部分明确划走，剩下的工作量其实相当可控。

## 二、准备工作

工具很简单：**编辑器**用 VS Code 或记事本都行（重点是手工敲代码），**浏览器**用 Chrome / Edge / Firefox 负责看效果和截图。

一个好消息是：**纯 HTML 作业不需要服务器**，双击 html 文件就能在浏览器里打开。如果本地装了 WAMP，也可以把文件丢进 `www` 目录，用 `http://localhost/xxx.html` 访问——两种方式截图都有效，不必纠结。

推荐的目录结构如下，把两个任务彻底分开，避免互相污染：

```text
web-lab1/
├── site/            ← 任务一：个人网站
│   ├── index.html
│   ├── profile.html
│   ├── experience.html
│   ├── books.html
│   ├── hobby.html
│   ├── grades.html
│   ├── links.html
│   └── css/
│       └── style.css      ← 唯一的外部样式表
└── bookshop/        ← 任务二：图书售卖界面
    └── main.html          ← 单文件，内部样式表
```

注意 `css/` 是 `site/` 的子目录，图片建议再开一个 `images/` 放照片——这个路径关系直接决定了后面 `<link>` 和 `<img>` 该怎么写。

## 三、任务一：个人主页（多页面 + 外部样式表）

### 3.1 八项内容与页面分配

指导书规定了 8 项必须出现的内容，它们的载体元素其实已经暗示了该用什么标签：

1. 标题"欢迎访问×××的主页"——放在 `index.html`，用 `<h1>` 和 `<title>` 各一份。
2. 个人简介，**必须包含图片**——放在 `profile.html`，用 `<p>` 加 `<img>`。
3. 个人经历简介，**用有序列表显示**——放在 `experience.html`，用 `<ol><li>`。
4. 最喜欢的 **4 本书**，**用无序列表显示**——放在 `books.html`，用 `<ul><li>`，数量必须恰好 4 本。
5. 个人兴趣简介——放在 `hobby.html`，段落文字或列表都行。
6. **6 门主干课程成绩**，用表格显示——放在 `grades.html`，列依次为课程名、开课学期、任课教师、分数。
7. 朋友主页链接或**学校主页链接**——放在 `links.html`，用 `<a href>`。
8. 其它想表达的信息（自由发挥）——放 `index.html` 或单独开一页，比如一句座右铭，或者一个留言表单（文本框 + 提交按钮即可，不需要后台）。

三条硬性约束：**8 项内容必须都能通过导航链接访问到**；**每个页面顶部放相同的导航栏**；页面之间不能有死链。

### 3.2 统一的页面骨架

七个页面结构完全一致，只是 `<title>` 和 `<main>` 里的内容不同。复制这段骨架然后替换中间内容即可：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>欢迎访问张三的主页</title>
  <link rel="stylesheet" href="css/style.css">   <!-- 外部样式表 -->
</head>
<body>
  <header><h1>欢迎访问张三的主页</h1></header>   <!-- 要求 (1) -->

  <nav>
    <a href="index.html">首页</a> |
    <a href="profile.html">个人简介</a> |
    <a href="experience.html">个人经历</a> |
    <a href="books.html">喜欢的书</a> |
    <a href="hobby.html">兴趣爱好</a> |
    <a href="grades.html">课程成绩</a> |
    <a href="links.html">友情链接</a>
  </nav>

  <main>
    <!-- 本页对应的内容条目 -->
  </main>

  <footer><p>版权所有 © 2026 张三</p></footer>
</body>
</html>
```

这份骨架本身就把"语义化"讲完了：`header` 承载标题、`nav` 承载导航、`main` 承载主体内容、`footer` 承载版权信息。`lang="zh-CN"` 和 `<meta charset="UTF-8">` 也不要省，前者影响读屏软件的朗读语言，后者决定中文是否乱码。

### 3.3 各页的核心写法

**profile.html——简介加照片。** 图片放在正文段落之前，`alt` 写上替代文字，`width` 控制尺寸：

```html
<h2>个人简介</h2>
<img src="images/me.jpg" alt="我的照片" width="200">
<p>我叫张三，计算机学院软件工程系 2024 级本科生，喜欢编程与篮球。</p>
```

**experience.html——个人经历用有序列表。** 经历本身有先后顺序，用 `ol` 才能让浏览器自动编号：

```html
<h2>个人经历</h2>
<ol>
  <li>2024.09 考入××大学软件工程系</li>
  <li>2025.09 加入校计算机协会</li>
  <li>2026.07 完成 C 语言课程设计</li>
</ol>
```

**books.html——4 本书用无序列表。** 注意是恰好 4 本，`ul` 不带编号：

```html
<h2>我最喜欢的 4 本书</h2>
<ul>
  <li>《算法导论》</li>
  <li>《计算机程序的构造和解释》</li>
  <li>《三体》</li>
  <li>《平凡的世界》</li>
</ul>
```

**hobby.html——兴趣爱好。** 这里最能看出"语义跟着内容走"：如果只是几项平行爱好，用段落或列表都行，不要为了排版硬套表格。

```html
<h2>兴趣爱好</h2>
<p>我平时喜欢打篮球、跑步；业余时间喜欢写小程序、看科技视频，
最近正在学习 HTML 和 CSS，希望做出自己的网站。</p>
```

**grades.html——6 门成绩用表格。** 列名要照指导书写全，表头用 `th`：

```html
<h2>主干课程成绩</h2>
<table>
  <tr><th>课程名</th><th>开课学期</th><th>任课教师</th><th>分数</th></tr>
  <tr><td>高等数学</td><td>2024 秋季</td><td>张老师</td><td>90</td></tr>
  <tr><td>离散数学</td><td>2025 春季</td><td>李老师</td><td>80</td></tr>
  <tr><td>程序设计基础</td><td>2024 秋季</td><td>王老师</td><td>85</td></tr>
  <tr><td>数据结构</td><td>2025 秋季</td><td>刘老师</td><td>88</td></tr>
  <tr><td>计算机组成原理</td><td>2026 春季</td><td>陈老师</td><td>82</td></tr>
  <tr><td>操作系统</td><td>2026 秋季</td><td>赵老师</td><td>86</td></tr>
</table>
```

**links.html——友情链接。** 外链建议加 `target="_blank"`，既不打断站内导航，也更符合用户预期：

```html
<h2>友情链接</h2>
<ul>
  <li><a href="https://www.xxx.edu.cn" target="_blank">我的大学主页</a></li>
  <li><a href="https://friend.example.com" target="_blank">朋友李四的主页</a></li>
</ul>
```

**要求 (8)**：自由发挥。在 `index.html` 加一段座右铭 `<p>`，或者做一个留言 `<form>`（一个文本框加一个提交按钮就够，不需要任何后台处理），都能满足。

### 3.4 外部样式表：统一样貌的唯一开关

任务一的所有样式都集中写在 `css/style.css` 这一个文件里。它是"多个页面共用一套外观"这件事的技术实现——**改一处，全站生效**，这正是任务二那种单文件写法做不到的事。

```css
body {
  font-family: "Microsoft YaHei", Arial, sans-serif;
  margin: 0;
  background: #f4f6f8;
  color: #333;
}
header {
  background: #2c5f8a;
  color: #fff;
  padding: 24px;
  text-align: center;
}
nav {
  background: #dfe9f2;
  padding: 10px;
  text-align: center;
}
nav a {
  text-decoration: none;
  color: #2c5f8a;
  margin: 0 8px;
}
nav a:hover { color: #e0562c; }
main {
  max-width: 900px;
  margin: 20px auto;
  background: #fff;
  padding: 24px;
  border-radius: 8px;
}
table {
  border-collapse: collapse;
  width: 100%;
}
table, th, td { border: 1px solid #999; }
th, td { padding: 8px; text-align: center; }
th { background: #eef3f8; }
footer {
  text-align: center;
  color: #888;
  padding: 16px;
}
```

这份样式的思路值得说一句：蓝白配色、无衬线字体、`body` 统一字体与浅灰背景，`header` 做蓝底白字居中横幅，`nav` 去掉链接下划线并用 `:hover` 给悬停反馈，`main` 用 `max-width: 900px` 配合 `margin: 20px auto` 限宽居中形成卡片式版面，成绩表用 `border-collapse: collapse` 合并边框、表头加底色。**这些选择本身完全可以换**，指导书只要求"字体颜色样式自己决定"，关键是能说清楚"我想要什么外观、用哪条规则实现它"——这也是报告里要写的那段话。

## 四、任务二：图书售卖界面（单文件 + 内部样式表）

### 4.1 十一项要求逐条对照

这项任务的指导书要求非常具体，一共 11 条，实现方式基本是唯一的：

1. HTML 标题为 "Welcome to book seller"——写进 `<title>`。
2. 页面第一行**黑体**显示 "You are welcome"——用 `<h1>`（`<h1>` 默认就是加粗显示）。
3. 提示 "please input your name" + 输入框——放在表格行内的 `<td>` 里嵌 `<input type="text">`。
4. 提示 "please input your address" + 输入框——同上。
5. 提示 "please input your zip" + 输入框——同上。
6. **黑体**显示 "please fill in the quantity field of the following form"——用 `<b>` 或 `<strong>`。
7. 四列表格：book / publisher / price / quantity。
8. quantity 用**输入框**输入——每行第 4 列放 `<input>`。
9. 显示 "payment method"——用 `<p>`。
10. **单选按钮**支付方式：cash / cheque / credit card——用 `<input type="radio">`。
11. 两个标准按钮：**submit** 和 **reset**——`<input type="submit">`、`<input type="reset">`。

图书数据照抄指导书表 4.1，四行分别是：

| book | publisher | price |
|------|-----------|-------|
| Web technology | Springer press | $5.0 |
| mathematics | ACM press | $6.2 |
| principle of OS | Science press | $10 |
| Theory of matrix | High education press | $7.8 |

> **一处需要澄清的地方：**指导书原文写的是"四个支付方式选项"，但实际只列了 cash、cheque、credit card 三种。本文按原文照抄这三种；如果想凑满四个，可以自行补一种并在报告里说明。

### 4.2 完整示例代码

把所有要求串起来，就是这样一个 `main.html`：

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Welcome to book seller</title>
  <style>
    body { font-family: Arial, sans-serif; background: #fafafa; margin: 0; }
    h1 {
      background: #1f6f43; color: #fff; text-align: center;
      padding: 16px; margin: 0; font-weight: bold;
    }
    .form-table, .book-table {
      border-collapse: collapse; width: 80%;
      margin: 16px auto; background: #fff;
    }
    .book-table, .book-table th, .book-table td { border: 1px solid #bbb; }
    .book-table th, .book-table td { padding: 8px; text-align: center; }
    .book-table th { background: #e3efe7; }
    .form-table td { padding: 6px 10px; }
    .center { text-align: center; }
    .btn { padding: 6px 24px; margin: 0 8px; }
  </style>
</head>
<body>
  <h1>You are welcome</h1>   <!-- 要求 (2) 黑体第一行 -->

  <form action="#" method="post">
    <!-- 要求 (3)(4)(5)：顾客信息，指导书建议 tr/td 嵌 input -->
    <table class="form-table">
      <tr><td>please input your name</td><td><input type="text" name="name"></td></tr>
      <tr><td>please input your address</td><td><input type="text" name="address" size="40"></td></tr>
      <tr><td>please input your zip</td><td><input type="text" name="zip"></td></tr>
    </table>

    <!-- 要求 (6) -->
    <p class="center"><b>please fill in the quantity field of the following form</b></p>

    <!-- 要求 (7)(8)：图书表，quantity 列为输入框 -->
    <table class="book-table">
      <tr><th>book</th><th>publisher</th><th>price</th><th>quantity</th></tr>
      <tr><td>Web technology</td><td>Springer press</td><td>$5.0</td>
          <td><input type="text" name="qty_web" size="5"></td></tr>
      <tr><td>mathematics</td><td>ACM press</td><td>$6.2</td>
          <td><input type="text" name="qty_math" size="5"></td></tr>
      <tr><td>principle of OS</td><td>Science press</td><td>$10</td>
          <td><input type="text" name="qty_os" size="5"></td></tr>
      <tr><td>Theory of matrix</td><td>High education press</td><td>$7.8</td>
          <td><input type="text" name="qty_matrix" size="5"></td></tr>
    </table>

    <!-- 要求 (9)(10)：支付方式单选按钮 -->
    <p class="center">payment method<br>
      <input type="radio" name="payment" value="cash" checked>cash
      <input type="radio" name="payment" value="cheque">cheque
      <input type="radio" name="payment" value="credit card">credit card
    </p>

    <!-- 要求 (11)：submit 与 reset -->
    <p class="center">
      <input type="submit" value="submit" class="btn">
      <input type="reset" value="reset" class="btn">
    </p>
  </form>
</body>
</html>
```

**这份示例里有三个容易忽略的细节：**

其一，顾客信息区用的是一张**没有边框的表格**，纯粹为了对齐"提示文字 + 输入框"两列。这是纯 HTML 时代的经典写法，指导书原本也是建议 `tr`/`td` 里嵌 `input`，照做即可，不要改成 `label` 也不用加 CSS 边框。

其二，四个 quantity 输入框的 `name` 各不相同（`qty_web`、`qty_math`、`qty_os`、`qty_matrix`），因为它们要提交的是**四个不同的值**；而三个支付方式的 `name` 完全相同（都是 `payment`），正因为同名，浏览器才让它们**互斥**——这也是判断 radio 分组是否正确的唯一标准。

其三，`action="#" method="post"` 保留占位即可，本次实验不要求任何后台处理；`reset` 按钮的作用是浏览器原生的一键清空，不需要写代码。

## 五、实验报告怎么写

打开模板《Web技术课内实验1-学号-姓名.doc》，按**设计方案**和**实现方案**两大部分填写。

### 设计方案

**网站结构示意图（任务一）。** 按导航关系画层级图，一眼看清每个页面承担哪项内容：

```text
个人网站 index.html（欢迎访问×××的主页）
├── profile.html      个人简介（含图片）
├── experience.html   个人经历（有序列表）
├── books.html        喜欢的 4 本书（无序列表）
├── hobby.html        兴趣爱好
├── grades.html       6 门课程成绩（表格）
└── links.html        友情链接
```

**body 元素树状图（任务二）。** 单页面用这个就够了，只需体现文档结构，表格注明到 `table` 节点即可，不必画到 `td`：

```text
body
├── h1（You are welcome）
└── form
    ├── table（顾客信息：name / address / zip 三个输入框）
    ├── b（please fill in ...）
    ├── table（图书表：book / publisher / price / quantity）
    ├── p（payment method + 3 个 radio）
    └── p（submit 按钮 + reset 按钮）
```

**样式表设计说明。** 这段是纯文字阐述，核心是"我想要什么外观，对应哪条 CSS 规则"。可以这样写：

> 网站整体采用蓝白配色、无衬线字体：`body` 用 `font-family` 统一字体、用 `background` 设置浅灰背景；页头 `header` 用 `background`、`color`、`text-align` 做成蓝底白字居中横幅；导航去掉下划线（`text-decoration: none`）并用 `:hover` 实现悬停变色；主体内容 `main` 限宽 900px 居中（`margin: 20px auto`）形成卡片式版面；成绩表用 `border-collapse: collapse` 合并边框，表头加底色。图书界面采用绿色主题，`h1` 黑体白字居中，两张表格分别控制顾客信息与图书列表的边框和间距。

### 实现方案

只有两条，但都是硬性要求：

1. **代码以文本形式复制进报告，不要截图代码。** 排版整齐、尽量紧凑——代码量大，截图既占体积又不可检索，还会直接撞上 1M 的限制。
2. **浏览器显示效果截图。** 每个页面（或至少代表性页面）在浏览器里打开后截图，需完整显示页面效果；图书界面截一张整体图即可，也可以再补一张填好数据的图，更直观。

### 提交前检查清单

- [ ] 任务一：内容 (1)~(8) 全部覆盖、分布在多个 HTML、外部样式表生效、导航互链无死链
- [ ] 任务二：11 项要求逐条对照无遗漏（尤其是标题文字、"You are welcome" 在第一行、四列图书表、quantity 输入框、三个 radio、submit + reset）
- [ ] 代码为手工输入，报告内代码是文本而非截图
- [ ] 文件名为 `Web技术课内实验1-学号-姓名`，word 或 pdf 格式，**体积 ≤ 1M**（截图过大时压缩分辨率或转 JPG）
- [ ] 10 月 30 日前提交到腾讯文档表单

## 六、五个常见问题

**外部样式表不生效？** 检查 `<link rel="stylesheet" href="css/style.css">` 的相对路径。按本文的目录结构，`style.css` 在 HTML 同级的 `css/` 子目录下就这么写；如果两者在同一目录，则直接写文件名。

**页面间链接 404？** 所有 HTML 放同一目录时，`<a href>` 直接写文件名即可；**文件名的大小写要和实际完全一致**——Linux 服务器和某些浏览器对大小写敏感，这是本地能跑、提交后挂掉的典型原因。

**图片不显示？** `<img src="images/me.jpg">` 的路径要对，并且用相对路径；jpg、png 都可以。

**两个 radio 能同时选中？** 检查这几个 radio 的 `name` 是否完全相同。**只有同名才会互斥**，名字各不相同就变成了四个独立的单选按钮，可以同时选中。

**报告超过 1M？** 压缩截图（降低分辨率、存为 JPG），或在导出 PDF 时选较低的图像质量。

## 写在最后

这次实验的技术含量说实话不高——没有 JavaScript，没有框架，没有后端，纯粹是 HTML 骨架加 CSS 装饰。但它把两件容易被忽略的事讲得很清楚：**标签的选择要跟着内容的语义走**（有顺序用 `ol`，无顺序用 `ul`，成绩这种二维数据用 `table`），以及**样式该放在哪里**（多个页面共享就放外部样式表并且只留一份，单页面就放 `<style>` 里）。

这两条判断标准，比记住任何一个具体属性都重要。后面从第四章的 PHP 表单处理开始，才会真正用到 `name` 属性、`reset` 的行为这些今天只是"照抄"的东西——现在把它们记住名字和含义，后面会省很多事。

祝实验顺利，10 月 30 日前交卷。