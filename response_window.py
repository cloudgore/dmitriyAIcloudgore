"""Ephemeral local answer viewer; content is received on stdin, never saved."""
import json
import os
import sys
import tkinter as tk
from tkinter import ttk
from web_search import public_link


def main():
    payload=json.loads(sys.stdin.buffer.read(64000).decode('utf-8'))
    window=tk.Tk()
    window.title('Ответ Джарвиса')
    window.geometry('720x460')
    frame=ttk.Frame(window,padding=16)
    frame.pack(fill='both',expand=True)
    ttk.Label(frame,text=payload.get('question','')[:250],wraplength=660,
              font=('Segoe UI',12,'bold')).pack(anchor='w',pady=(0,10))
    ttk.Button(frame,text='Закрыть',command=window.destroy).pack(side='bottom',anchor='e',pady=(10,0))
    body=ttk.Frame(frame)
    body.pack(fill='both',expand=True)
    text=tk.Text(body,wrap='word',font=('Segoe UI',11),relief='flat',padx=5,pady=5,height=8)
    scroll=ttk.Scrollbar(body,orient='vertical',command=text.yview)
    scroll.pack(side='right',fill='y')
    text.config(yscrollcommand=scroll.set)
    text.pack(side='left',fill='both',expand=True)
    text.insert('end',payload.get('answer','')[:5000])
    sources=payload.get('sources',[])[:3]
    if sources:
        text.insert('end','\n\nИсточники:\n')
    for i,source in enumerate(sources):
        url=source.get('url','')
        if not public_link(url):
            continue
        tag='source'+str(i)
        text.insert('end',f"{i+1}. {source.get('title','Источник')}\n{url}\n",tag)
        text.tag_config(tag,foreground='#0066bb',underline=True)
        text.tag_bind(tag,'<Button-1>',lambda event,target=url:os.startfile(target))
        text.tag_bind(tag,'<Enter>',lambda event:text.config(cursor='hand2'))
        text.tag_bind(tag,'<Leave>',lambda event:text.config(cursor='arrow'))
    text.config(state='disabled')
    window.mainloop()


if __name__=='__main__':
    main()
