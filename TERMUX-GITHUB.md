# رفع Peche TN من Termux — أمر واحد يعمل (HTTPS + توكن)

> الإصدار الحالي: **1.10.0** (المحرك `1.6.8`، schema `3.9`). الملف المطلوب: `peche-tn-v1.10.0.zip`.

تحتاج ملفاً واحداً فقط:

- `peche-tn-v1.10.0.zip`

ضعه في مجلد **Download** بالاسم نفسه. يفك الأرشيف إلى `peche-tn/`، ويتضمن `.env.example` توثيقياً بلا أسرار أو مفتاح Gemini، ولا يحتوي `.git` أو ملفات `.env` المحلية أو dependencies أو build artifacts.

---

## 1) تجهيز التوكن (مرة واحدة فقط)

1. افتح: **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token (classic)**.
2. الصلاحيات المطلوبة:
   - `repo` (لمستودع خاص) أو `public_repo` (لمستودع عام).
   - `workflow` (لرفع ملفات GitHub Actions الموجودة في `.github/workflows/`).
3. انسخ التوكن — يظهر **مرة واحدة** فقط.

> لا تكتب التوكن في أي محادثة، ولا ترفعه داخل ملفات المستودع، ولا ترسله لأحد. إن تسرّب، احذفه من GitHub وأنشئ غيره فوراً.

---

## 2) الأمر الكامل (الصقه كاملاً بعد وضع التوكن)

```bash
pkg install -y git unzip

[ -d "$HOME/storage/downloads" ] || termux-setup-storage

TOKEN="ضع_التوكن_هنا"

A="$HOME/storage/downloads/peche-tn-v1.10.0.zip"

case "$TOKEN" in
  ""|"ضع_التوكن_هنا") echo "خطأ: ضع التوكن الحقيقي مكان ضع_التوكن_هنا"; exit 1 ;;
esac

set -e

test -f "$A" || { echo "خطأ: لم أجد $A — انقل ملف ZIP إلى مجلد Download ثم أعد اللصق"; exit 1; }

rm -rf "$HOME/peche-tn"
unzip -q "$A" -d "$HOME"
cd "$HOME/peche-tn"

git init
git checkout -B main
git config user.name "naderba69"
git config user.email "balinader@gmail.com"
git add -A
git commit -m "Release Peche TN v1.10.0"
git remote add origin "https://naderba69:${TOKEN}@github.com/naderba69/peche-tn.git"

git push --force -u origin main
git push --force origin main:master 2>/dev/null || true

echo ""
echo "تم الرفع بنجاح"
```

**ماذا يفعل:** يُنشئ سجلّاً جديداً نظيفاً كل مرة (لا `.git` قديم داخل الأرشيف)، يضيف كل ملفات النسخة، ثم يرفعها قسرياً فوق `main` (و`master` كاحتياط للمستودعات القديمة). `--force` مقصود لأن السجل يُعاد بناؤه من الأرشيف عند كل إصدار.

> **بعد الرفع:** التوكن يبقى مخزناً في `.git/config` على هاتفك. لمسحه دون كسر المستودع:
> ```bash
> cd "$HOME/peche-tn" && git remote set-url origin https://github.com/naderba69/peche-tn.git
> ```

---

## 3) التحقق بعد أن تصبح الخدمة Live (Render)

```bash
cd "$HOME/peche-tn" && python scripts/smoke_deployment.py https://peche-tn-xxxx.onrender.com
```

كلمة `Live` وحدها لا تكفي؛ النجاح الحقيقي هو ظهور `ALL PASS`.

---

## بديل بمفتاح SSH (بدون توكن)

إن فضّلت مفتاح SSH بدل التوكن:

```bash
ssh-keygen -t ed25519 -C "balinader@gmail.com" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

ألصق المفتاح في **GitHub → Settings → SSH and GPG keys → New SSH key**، ثم:

```bash
A="$HOME/storage/downloads/peche-tn-v1.10.0.zip"
rm -rf "$HOME/peche-tn"
unzip -q "$A" -d "$HOME"
cd "$HOME/peche-tn"
git init && git checkout -B main
git config user.name "naderba69"
git config user.email "balinader@gmail.com"
git add -A
git commit -m "Release Peche TN v1.10.0"
git remote add origin git@github.com:naderba69/peche-tn.git
git push --force -u origin main
```

---

## نشر Render

بعد نجاح `push` افتح الرابط واتبع الخطوات في [`RENDER.md`](RENDER.md):

<https://render.com/deploy?repo=https%3A%2F%2Fgithub.com%2Fnaderba69%2Fpeche-tn>

لا تضف مفتاح Gemini أو أي Environment Variable. الواجهة وFastAPI يعملان معاً داخل Docker واحد.
