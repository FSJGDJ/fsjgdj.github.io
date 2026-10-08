---
title: '我的 Web 技术实验 1：做一个多页面站，再做一个单文件表单'
description: '把《Web技术（双语）》实验 1 的两道题拆开讲清楚——个人主页为什么用外部样式表、图书售卖界面为什么只能塞进一个文件、报告里的三张图怎么画，以及我提前想明白的几个坑。'
pubDate: 2026-10-08
tags: ['Web技术', 'HTML', 'CSS', '实验报告']
---


## 我为什么先花半小时读要求，而不是直接开写

拿到实验 1 的要求，第一反应是"不就是做个网页"。但把指导书第三、四章翻完，我意识到这次实验真正想问的东西不是"你会不会写 HTML"——它一共就两件事，而且这两件事被刻意设计成了同一个知识点的正反面。

正面是第三章实验内容 1：**个人主页**。八项指定内容，拆到多个 HTML 文件里，所有页面的样式收在**一份外部样式表**里，页面之间靠超链接串起来。

反面是第四章实验内容 1：**图书售卖界面**。所有内容塞进**一个 HTML 文件**，样式写在页面内部的 `<style>` 标签里，不许外链。

也就是说，这次实验一半在考"多个页面怎么共享一套样式"，另一半在考"一个页面内部怎么管自己的样式"。这两句话想清楚，剩下的都是体力活。

另一件值得先说的事：**这次不用写 JavaScript，也没有后端。** 想清楚这一点，才不会在错误的方向上浪费时间。

## 一、先把边界划死：哪些明确不用做

这是我读要求时花时间最多、也最值的一段。指导书里列的实验内容很长，但本次只做其中一部分：

- 第三章的**实验内容 2**——用 JavaScript 求一元二次方程 ax²+bx+c=0 的根——**本次不要求**，只做实验内容 1。
- 第四章的**实验内容 2、3、4**——main.php 生成订单页、用 fwrite 写文件、用 reset 清空——**本次同样不要求**，只做实验内容 1 这个静态页面。

这直接意味着：任务二的表单**不需要任何后台**。`action` 属性留空或者随手填个 `#` 就行，不会有人真的去接收它。

另外指导书备注里有两句硬要求，我单独拎出来记着：**代码必须手工输入**（不接受工具生成），以及**多个页面之间要能互相链接访问**——后半句基本就是任务一的评分点。

## 二、我准备的目录结构

编辑器用 VS Code 或记事本都行（手工输入这条要求下，两者没有本质区别），浏览器用 Chrome 或 Edge 看效果、截图。

有一个好消息值得写在这儿：**纯 HTML 作业不需要服务器。** 双击 html 文件就能在浏览器里跑，截图完全有效。当然如果本地装了 WAMP，把文件丢进 `www` 目录用 `http://localhost/xxx.html` 访问也可以，两种方式都算数。

我把两个任务彻底分开，避免后面互相干扰：

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

特意把 `css/` 建成 `site/` 的子目录、照片另开一个 `images/`，是因为这两层路径关系直接决定后面 `<link>` 和 `<img>` 里的地址怎么写。先定结构再动手，比写完再回头改路径省事得多。

## 三、任务一：我的个人主页怎么拆

### 八项内容，我按"内容性质"分页

指导书规定了 8 项必须出现的内容。我没有随便分，而是按内容性质挑标签——它给的每一项其实都暗示了该用什么元素：

1. 标题"欢迎访问×××的主页"——落在 `index.html`，`<title>` 和 `<h1>` 各要一份。
2. 个人简介，必须带照片——`profile.html`，`<p>` 配 `<img>`。
3. 个人经历简介，要用**有序列表**——`experience.html`，`<ol>` 加 `<li>`。
4. 最喜欢的 **4 本书**，要用**无序列表**——`books.html`，`<ul>` 加 `<li>`，数量要正好 4 本。
5. 个人兴趣简介——`hobby.html`，段落或列表都行。
6. **6 门课程成绩**，要用表格——`grades.html`，列依次是课程名、开课学期、任课教师、分数。
7. 朋友主页或学校主页链接——`links.html`，用 `<a href>`。
8. 自己想表达的内容，自由发挥——放 `index.html` 或单独开一页。

关于第 8 项我一开始想复杂了，后来发现它其实是个送分项：在首页加一段座右铭 `<p>`，或者放一个留言 `<form>`（一个文本框加一个提交按钮就够，不用任何后台处理），都算完成。

还有三条不能忘的约束：**8 项内容都要能被导航点到**、**每个页面顶部放同一套导航栏**、**页面之间不能有死链**。

### 一套骨架，七个页面复用

七个页面结构完全一样，区别只在 `<title>` 和 `<main>` 里的内容。我的做法是先写一套骨架，之后每开一页就复制、只换这两处：

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

这段骨架其实已经替我把"语义化"讲完了：`header` 装标题、`nav` 装导航、`main` 装主体、`footer` 装版权，各司其职。`lang="zh-CN"` 和 `<meta charset="UTF-8">` 我也没省——前者影响读屏软件用什么语言去读，后者决定中文会不会乱码。

### 各页的具体写法

**个人简介页**——照片放在正文段落之前，`alt` 必须写，`width` 控制大小：

```html
<h2>个人简介</h2>
<img src="images/me.jpg" alt="我的照片" width="200">
<p>我叫张三，计算机学院软件工程系 2024 级本科生，喜欢编程与篮球。</p>
```

**个人经历页**——经历本身有先后顺序，所以我用 `ol` 让浏览器自动编号：

```html
<h2>个人经历</h2>
<ol>
  <li>2024.09 考入××大学软件工程系</li>
  <li>2025.09 加入校计算机协会</li>
  <li>2026.07 完成 C 语言课程设计</li>
</ol>
```

**书单页**——4 本书之间没有顺序，用 `ul`，数量按要求的 4 本写死：

```html
<h2>我最喜欢的 4 本书</h2>
<ul>
  <li>《算法导论》</li>
  <li>《计算机程序的构造和解释》</li>
  <li>《三体》</li>
  <li>《平凡的世界》</li>
</ul>
```

**兴趣爱好页**——这一页最能看出"标签跟着内容走"：如果只是几项平行的爱好，段落或列表都行，不需要为了排版硬套别的结构。

```html
<h2>兴趣爱好</h2>
<p>我平时喜欢打篮球、跑步；业余时间喜欢写小程序、看科技视频，
最近正在学习 HTML 和 CSS，希望做出自己的网站。</p>
```

**成绩页**——列名照指导书写全，表头用 `th`，正好 6 行数据：

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

**友情链接页**——外链我加了 `target="_blank"`，这样点出去不会把我自己的站顶掉：

```html
<h2>友情链接</h2>
<ul>
  <li><a href="https://www.xxx.edu.cn" target="_blank">我的大学主页</a></li>
  <li><a href="https://friend.example.com" target="_blank">朋友李四的主页</a></li>
</ul>
```

### 外部样式表：这个文件才是"外部"两个字的全部意义

任务一所有样式都集中在 `css/style.css`。它是"七个页面共用一套外观"的技术实现——**改一处，七个页面一起变**。这正是任务二那个单文件写法做不到的事，也是这两道题放一起的真正原因。

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

说一下我这份样式里每一步在想什么：`body` 统一字体、抹掉默认外边距、给个浅灰底；`header` 用蓝底白字居中做成一条横幅；`nav` 去掉链接下划线，再用 `:hover` 给个变色反馈，让人知道那行字是可以点的；`main` 用 `max-width: 900px` 配合 `margin: 20px auto` 限宽居中，做出卡片的感觉；成绩表用 `border-collapse: collapse` 把边框合并成一条线，表头补一层底色。

这些选择**指导书并没有规定**——原话是"字体颜色样式自己决定"。所以换配色、换字体都完全可以，真正要在报告里说清楚的是"我想要什么外观、用哪条规则实现了它"。

## 四、任务二：一个文件装完的图书售卖界面

这项任务的指导书要求细到近乎苛刻，一共 11 条，实现方式基本只有一种：

1. HTML 标题为 "Welcome to book seller"——写进 `<title>`。
2. 页面第一行**黑体**显示 "You are welcome"——用 `<h1>`（它默认就是加粗的）。
3. 提示 "please input your name" 加输入框——表格的 `<td>` 里嵌 `<input type="text">`。
4. 提示 "please input your address" 加输入框——同上。
5. 提示 "please input your zip" 加输入框——同上。
6. **黑体**显示 "please fill in the quantity field of the following form"——用 `<b>` 或 `<strong>`。
7. 四列表格：book / publisher / price / quantity。
8. quantity 用**输入框**输入——每行第 4 列放 `<input>`。
9. 显示 "payment method"——用 `<p>`。
10. **单选按钮**选支付方式：cash / cheque / credit card。
11. 两个标准按钮：**submit** 和 **reset**。

图书数据照指导书表 4.1 抄，四行是：

| book | publisher | price |
|------|-----------|-------|
| Web technology | Springer press | $5.0 |
| mathematics | ACM press | $6.2 |
| principle of OS | Science press | $10 |
| Theory of matrix | High education press | $7.8 |

### 完整代码

把 11 条串起来就是这个文件：

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

### 三个我特意留意的地方

**顾客信息那张表是不带边框的。** 它纯粹是为了把"提示文字 + 输入框"对齐成两列，指导书原本也是建议在 `tr`/`td` 里嵌 `input`，照做就好。别自作聪明改成 `label`，也别给它加边框样式——加了下拉不对齐反而更丑。

**四个 quantity 输入框的 `name` 各不相同，三个 radio 的 `name` 完全相同。** 这两句是反着来的，但原因一致：quantity 要提交四个**不同的值**，所以必须四个名字；支付方式三个选项只能选**一个**，所以必须同名——浏览器靠 `name` 相同来判断"这几个是一组、互相排斥"。这也是检查 radio 分组对不对的唯一标准。

**`action="#" method="post"` 是占位。** 本次实验不需要任何后台，`reset` 按钮清空表单也是浏览器原生行为，不用写代码。

## 五、我的实验报告怎么写

### 设计方案：三张图加一段话

**网站结构示意图**——按导航关系画层级，一眼看清每个页面承担什么：

```text
个人网站 index.html（欢迎访问×××的主页）
├── profile.html      个人简介（含图片）
├── experience.html   个人经历（有序列表）
├── books.html        喜欢的 4 本书（无序列表）
├── hobby.html        兴趣爱好
├── grades.html       6 门课程成绩（表格）
└── links.html        友情链接
```

**body 元素树状图**——任务二是单页面，画这个就够了。指导书只要求体现文档结构，表格标到 `table` 节点就行，不用细到 `td`：

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

**样式表设计说明**——纯文字，核心是"我要什么外观、对应哪条规则"。我打算就这么写：

> 网站整体采用蓝白配色、无衬线字体：`body` 用 `font-family` 统一字体、用 `background` 设置浅灰背景；页头 `header` 用 `background`、`color`、`text-align` 做成蓝底白字居中横幅；导航去掉下划线（`text-decoration: none`）并用 `:hover` 实现悬停变色；主体内容 `main` 限宽 900px 居中（`margin: 20px auto`）形成卡片式版面；成绩表用 `border-collapse: collapse` 合并边框，表头加底色。图书界面采用绿色主题，`h1` 黑体白字居中，两张表格分别控制顾客信息与图书列表的边框和间距。

### 实现方案：只有两条，但都是硬要求

**一是代码要以文本形式贴进报告，不能截图。** 代码量不小，截图既占体积又没法检索，还会直接撞上 1MB 的上限。

**二是浏览器效果截图。** 每个页面（或至少代表性页面）在浏览器里打开后截图，要完整显示页面效果；图书界面截一张整体图就行，想更直观可以再补一张填好数据的。

### 我提交前会过一遍的清单

- [ ] 任务一：8 项内容全覆盖、分布在多个 HTML、外部样式表确实生效、导航互链没有死链
- [ ] 任务二：11 条逐条对过（尤其标题文字、"You are welcome" 在第一行、四列图书表、quantity 输入框、三个 radio、submit 加 reset）
- [ ] 代码是手工输入的，报告里是文本而不是截图
- [ ] 文件名 `Web技术课内实验1-学号-姓名`，word 或 pdf，**不超过 1MB**
- [ ] 10 月 30 日前交到腾讯文档表单
