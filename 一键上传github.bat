chcp 65001 >nul

set /p "msg=请输入commit信息（直接回车为默认）："

if not defined msg set "msg=这个人很懒 什么都没有留下~"

git pull --rebase --autostash
git add .
git commit -m "%msg%"
git push

cmd /k