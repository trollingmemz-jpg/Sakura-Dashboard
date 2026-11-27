import sys
import tkinter as tk
from tkinter import ttk, colorchooser, filedialog, messagebox
import threading
import queue
from pathlib import Path
from engine import Engine

class App:
    def __init__(self, root):
        self.root=root; self.engine=Engine(); self.results=queue.Queue(); self.color=(244,120,215)
        root.title('Sakura RGB Engine'); root.geometry('950x560'); root.minsize(660,420)
        root.configure(bg='#1b1225')
        style=ttk.Style(); style.theme_use('clam'); style.configure('Treeview',background='#24192f',fieldbackground='#24192f',foreground='#f5d9ef',rowheight=28); style.configure('Treeview.Heading',background='#392842',foreground='#f5d9ef'); style.map('Treeview',background=[('selected','#85507e')]); style.configure('TButton',padding=8)
        tk.Label(root,text='桜  /  SAKURA RGB ENGINE',font=('Segoe UI',22,'bold'),fg='#f478d7',bg='#1b1225').pack(anchor='w',padx=22,pady=(18,4))
        tk.Label(root,text='Native hardware discovery and lighting',fg='#cdb4d4',bg='#1b1225').pack(anchor='w',padx=22)
        frame=ttk.Frame(root); frame.pack(fill='both',expand=True,padx=22,pady=16)
        self.tree=ttk.Treeview(frame,columns=('name','type','id','status'),show='headings',selectmode='browse')
        for key,title,width in [('name','Device',255),('type','Connection',105),('id','Hardware ID',110),('status','Driver status',300)]:
            self.tree.heading(key,text=title);self.tree.column(key,width=width,minwidth=70)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=self.tree.yview); self.tree.configure(yscrollcommand=scroll.set); scroll.pack(side='right',fill='y');self.tree.pack(fill='both',expand=True)
        buttons=ttk.Frame(root);buttons.pack(fill='x',padx=22)
        self.scan=ttk.Button(buttons,text='Scan hardware',command=self.refresh);self.scan.pack(side='left')
        self.apply=ttk.Button(buttons,text='Set colour',command=self.choose,state='disabled');self.apply.pack(side='left',padx=8)
        self.export=ttk.Button(buttons,text='Save support report',command=self.save,state='disabled');self.export.pack(side='right')
        self.status=tk.StringVar(value='Ready');tk.Label(root,textvariable=self.status,bg='#1b1225',fg='#e0c9e5',wraplength=850,justify='left').pack(anchor='w',padx=22,pady=12)
        self.tree.bind('<<TreeviewSelect>>',self.selection);self.refresh();root.after(100,self.poll)
    def refresh(self):
        self.scan.configure(state='disabled');self.apply.configure(state='disabled');self.export.configure(state='disabled');self.status.set('Scanning hardware without sending device commands…')
        def work():
            try:self.engine.scan();self.results.put(None)
            except Exception as e:self.results.put(type(e).__name__)
        threading.Thread(target=work,daemon=True).start()
    def poll(self):
        try:error=self.results.get_nowait()
        except queue.Empty:pass
        else:
            self.tree.delete(*self.tree.get_children())
            for i,d in enumerate(self.engine.devices):self.tree.insert('', 'end',iid=str(i),values=(d.name,d.kind,d.identifier,d.status))
            self.scan.configure(state='normal');self.export.configure(state='normal');self.status.set('Scan failed: '+error if error else f'{len(self.engine.devices)} interfaces / modules found. '+ ' '.join(self.engine.notes))
        self.root.after(100,self.poll)
    def selection(self,event=None):
        selected=self.tree.selection(); writable=bool(selected and self.engine.devices[int(selected[0])].kind=='Linux LED' and str(self.scan['state'])!='disabled'); self.apply.configure(state='normal' if writable else 'disabled')
    def choose(self):
        selected=self.tree.selection()
        if not selected:return
        rgb,_=colorchooser.askcolor(initialcolor='#%02x%02x%02x'%self.color,parent=self.root)
        if rgb is None:return
        try:self.color=tuple(round(x) for x in rgb);self.engine.set_color(self.engine.devices[int(selected[0])],self.color);self.status.set('Colour applied.')
        except (OSError,ValueError) as e:messagebox.showerror('Lighting',str(e))
    def save(self):
        path=filedialog.asksaveasfilename(defaultextension='.json',initialfile='Sakura-RGB-report.json',filetypes=[('JSON report','*.json')]);
        if path:
            try:Path(path).write_text(self.engine.report(),encoding='utf-8');self.status.set('Report saved. Review it before sharing.')
            except OSError as e:messagebox.showerror('Report',str(e))
if __name__=='__main__':
    if '--scan' in sys.argv:
        engine=Engine();engine.scan();print(engine.report())
    else:
        root=tk.Tk();App(root);root.mainloop()
