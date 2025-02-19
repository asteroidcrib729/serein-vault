from tkinter import messagebox, filedialog, Text, Entry, Button, Label, Tk, Toplevel, GROOVE
import pyperclip
import json
import os
from cryptography.fernet import Fernet
from hashlib import sha3_512
from base64 import b64encode, b64decode

class Hasher(Tk):
    def __init__(self):
        super().__init__()

        self.__File_Keys_Dict = dict()
        self.__Message_Keys_Dict = dict()
        self.__Stored_Password_Hash = str()

        self.__Default_Password = "_!@#ENC_Tool$%^_"

        self.__Hash = sha3_512()
        self.__Hash.update(b64encode(self.__Default_Password.encode()))
        self.__Combined_Hash = self.__Hash.hexdigest()

        if os.path.exists('File_Keys.json'):
            with open('File_Keys.json', 'r') as ReadFile:
                Raw_File_Encryption_Data = ReadFile.readlines()
                for i in Raw_File_Encryption_Data:
                    self.__File_Keys_Dict = json.loads(i)

        if os.path.exists('Message_Keys.json'):
            with open('Message_Keys.json', 'r') as ReadFile:
                self.__Message_Keys_Dict = json.load(ReadFile)

        if os.path.exists('Pass.txt'):
            with open("Pass.txt", "r") as ReadFile:
                self.__Stored_Password_Hash = ReadFile.readline().strip()
                self.Encryptor_Tool_Window()
        else:
            self.Set_Password_Window()

    def __Generate_Encryption_Key(self):
        return Fernet.generate_key()


    def Set_Password_Window(self):
        self.title("Set Password")
        self.minsize(width=448, height=170)
        self.maxsize(width=448, height=170)
        self.configure(bg="#292929")

        self.Label01 = Label(
            text="NOTE: PLEASE SET A PASSWORD TO ACCESS OPERATIONS\n"
                 "OF ENCRYPTION TOOL.  PASSWORD MUST BE AT LEAST 8\n"
                 "CHARACTERS AND SHOULD  CONTAIN  LETTERS  SYMBOLS\n"
                 "AND NUMBERS.",
            height=3, width=48, bg="black", fg="white", font=("Consolas", 12), justify="left"
        )
        self.Label01.place(x=5, y=5)

        self.Password = Entry(
            width=48, bd=0, font=("arial", 12), bg="black", show="*", fg="white",
            highlightthickness=2, highlightcolor="#fcfbf8",highlightbackground="#fcfbf8"
        )
        self.Password.place(x=7, y=90)

        self.Set_Button = Button(
            text="Set Password", height="2", width=61, bg="green", fg="white", bd=0,
            command=self.__Write_Password
        )
        self.Set_Button.place(x=8, y=120)

        return None

    def Encryptor_Tool_Window(self):
        for Wid in self.winfo_children():
            Wid.destroy()

        self.title("Encryptor Tool")
        self.minsize(width=370, height=375)
        self.maxsize(width=370, height=375)
        self.configure(bg="#292929")

        self.Label_01 = Label(
            text="ENTER A MESSAGE TO ENCRYPT OR DECRYPT", fg="white", bg="#141b21", font=("Roboto", 11, "bold")
        )
        self.Label_01.place(x=6, y=10)

        self.Message_Entry = Text(
            font="Roboto 11", relief=GROOVE, bd=0, fg="white", bg="black",
            highlightthickness=2, highlightcolor="#fcfbf8",highlightbackground="#fcfbf8"
        )
        self.Message_Entry.place(x=11, y=40, width=348, height=100)

        self.Label_02 = Label(
            text="ENTER PASSWORD TO START PROCESS", fg="white", bg="#141b21", font=("Roboto", 11, "bold")
        )
        self.Label_02.place(x=31, y=150)

        self.Password_Entry = Entry(
            width=43, bd=0, font=("arial", 11), bg="black", show="*", fg="white",
            highlightthickness=2, highlightcolor="#fcfbf8",highlightbackground="#fcfbf8"
        )
        self.Password_Entry.place(x=12, y=180)

        self.Button_01 = Button(
            text="Encrypt Message", height=2, width=18, bg="black", fg="white", bd=0,font=("Roboto", 11, "bold"),
            activebackground="#292929", activeforeground="white",
            command=self.Encrypt_message
        )
        self.Button_01.place(x=10, y=215)

        self.Button_02 = Button(
            text="Decrypt Message", height=2, width=18, bg="black", fg="white", bd=0,font=("Roboto", 11, "bold"),
            activebackground="#292929", activeforeground="white",
            command=self.Decrypt_Message
        )
        self.Button_02.place(x=192, y=215)

        self.Button_03 = Button(
            text="Change Password",font=("Roboto", 11, "bold"), height=2, width="20", bg="black", fg="white", bd=0,
            activebackground="#292929", activeforeground="white",
            command=self.Change_Password
        )
        self.Button_03.place(x=95, y=270)

        self.Button_04 = Button(
            text="Encrypt File", height=2, width=18, bg="black", fg="white", bd=0,font=("Roboto", 11, "bold"),
            activebackground="#292929", activeforeground="white",
            command=self.Encrypt_File
        )
        self.Button_04.place(x=10, y=324)

        self.Button_05 = Button(
            text="Decrypt File", height=2, width=18, bg="black", fg="white", bd=0,font=("Roboto", 11, "bold"),
            activebackground="#292929", activeforeground="white",
            command=self.Decrypt_File
        )
        self.Button_05.place(x=192, y=324)

    def __Write_File_Keys(self):
        with open('File_Keys.json', 'w') as WriteFile:
            json.dump(self.__File_Keys_Dict, WriteFile)

    def __Write_Message_Keys(self):
        with open('Message_Keys.json', 'w') as WriteFile:
            json.dump(self.__Message_Keys_Dict, WriteFile)

    def __Write_Password(self):
        Input = self.Password.get()
        if Input.isascii() and len(Input) >= 8:
            Encoded_Password = b64encode(Input.encode("utf-8"))

            Hash = sha3_512()
            Hash.update(Encoded_Password)
            self.__Stored_Password_Hash = Hash.hexdigest()

            self.__Combined_Hash = self.__Stored_Password_Hash

            with open("Pass.txt", "w") as File:
                File.write(self.__Combined_Hash)

                messagebox.showinfo("SUCCESS", "PASSWORD SET SUCCESSFULLY!")

                return self.Encryptor_Tool_Window()

        else:
            return messagebox.showerror(
                "ERROR", "ENTER A VALID PASSWORD! PASSWORD MUST BE AT LEAST 8 CHARACTERS"

            )

    def Change_Password(self):
        self.Change_Password_Screen = Toplevel()
        self.Change_Password_Screen.title("Change Password")
        self.Change_Password_Screen.minsize(width=355, height=170)
        self.Change_Password_Screen.maxsize(width=355, height=170)
        self.Change_Password_Screen.configure(bg="#292929")

        Label01 = Label(
            self.Change_Password_Screen, text="ENTER CURRENT PASSWORD", bg="black", fg="white",
            font=("Roboto", 13, "bold")
        )
        Label01.place(x=50, y=5)

        self.Current_Password = Entry(
            self.Change_Password_Screen, width=38, bd=0, font=("arial", 12), bg="black", show="*", fg="white",
            highlightthickness=2, highlightcolor="white",highlightbackground="white"
        )
        self.Current_Password.place(x=5, y=35)

        Label02 = Label(self.Change_Password_Screen, text="ENTER NEW PASSWORD", bg="black", fg="white",
                        font=("Roboto", 13, "bold"))
        Label02.place(x=70, y=65)

        self.New_Password = Entry(
            self.Change_Password_Screen, width=38, bd=0, font=("arial", 12), bg="black", show="*", fg="white",
            highlightthickness=2, highlightcolor="white",highlightbackground="white"
        )
        self.New_Password.place(x=5, y=95)

        Update_Button = Button(self.Change_Password_Screen, text="Update Password", height="2", width=24, bg="green",
                               fg="white",font=("roboto",10,"bold"), bd=0, command=self.Password_Manipulator
                               )
        Update_Button.place(x=85, y=125)

    def Password_Manipulator(self):
        self.__Current_Password = self.Current_Password.get()
        self.__New_Password = self.New_Password.get()

        Hash01 = sha3_512()
        Hash01.update(b64encode(self.__Current_Password.encode("utf-8")))
        self.__Current_Password_Hash = Hash01.hexdigest()

        if self.__Current_Password_Hash == self.__Stored_Password_Hash and len(self.__New_Password) >= 8:
            Hash02 = sha3_512()
            Hash02.update(b64encode(self.__New_Password.encode("utf-8")))
            self.__Stored_Password_Hash = Hash02.hexdigest()

            with open("Pass.txt", "w") as WriteFile:
                WriteFile.write(self.__Stored_Password_Hash)
                self.Change_Password_Screen.destroy()
                messagebox.showinfo("SUCCESS", "PASSWORD CHANGED SUCCESSFULLY!")

                return self.Encryptor_Tool_Window()

        elif len(self.__New_Password) < 8:
            return messagebox.showerror(
                "ERROR",
                "NEW PASSWORD MUST BE AT LEAST 8 CHARACTERS LONG AND SHOULD CONTAIN LETTERS SYMBOLS AND NUMBERS!"
            )

        else:
            return messagebox.showerror("ERROR", "INVALID CURRENT PASSWORD!")

    def Encrypt_message(self):
        Raw_Message = self.Message_Entry.get("1.0", "end-1c").strip()
        Password = self.Password_Entry.get().strip()

        if Password.isascii() and len(Password) >= 8:
            Hash = sha3_512()
            Hash.update(b64encode(Password.encode("utf-8")))
            Password_Hash = Hash.hexdigest()

            if Password_Hash == self.__Stored_Password_Hash:
                if len(Raw_Message) != 0:
                    self.__Message_Keys_Dict.clear()
                    Key = self.__Generate_Encryption_Key()
                    FerNet = Fernet(Key)

                    Encrypted_Message = FerNet.encrypt(Raw_Message.encode())
                    Encrypted_Message = b64encode(Encrypted_Message).decode("utf-8")
                    self.__Message_Keys_Dict[Encrypted_Message] = Key.decode("utf-8")

                    self.__Write_Message_Keys()
                    pyperclip.copy(Encrypted_Message)

                    messagebox.showinfo(
                        "SUCCESS",
                        "MESSAGE ENCRYPTED SUCCESSFULLY!\n\nTHE ENCRYPTED MESSAGE HAS BEEN COPIED TO CLIPBOARD."
                    )

                else:
                    messagebox.showerror("ERROR", "PLEASE ENTER A VALID MESSAGE TO ENCRYPT!")

            else:
                messagebox.showerror("ERROR", "INVALID PASSWORD!")

        else:
            messagebox.showerror(
                "ERROR",
                "INVALID PASSWORD ENTERED!\nPLEASE ENTER A PASSWORD OF AT LEAST 8 CHARACTERS CONTAINING LETTERS SYMBOLS AND NUMBERS!"
            )

    def Decrypt_Message(self):
        Password = self.Password_Entry.get().strip()
        Secret_Key_File = filedialog.askopenfilename(title="Select Secret Key File")

        if Password.isascii() and len(Password) >= 8:
            Hash = sha3_512()
            Hash.update(b64encode(Password.encode("utf-8")))
            Password_Hash = Hash.hexdigest()

            if Password_Hash == self.__Stored_Password_Hash:
                try:
                    with open(Secret_Key_File, "r") as f:
                        secret_key_data = json.load(f)

                    # Assuming the JSON data is in the format {"encrypted_message": "encryption_key"}
                    if len(secret_key_data) == 1:
                        encrypted_message, encryption_key = next(iter(secret_key_data.items()))

                        decoded_message = b64decode(encrypted_message.encode())
                        fernet = Fernet(encryption_key.encode("utf-8"))

                        decrypted_message = fernet.decrypt(decoded_message).decode("utf-8")
                        self.Message_Entry.delete("1.0", "end")
                        self.Message_Entry.insert("1.0", decrypted_message)

                        messagebox.showinfo("SUCCESS", "MESSAGE DECRYPTED SUCCESSFULLY!")

                    else:
                        messagebox.showerror("ERROR", "Invalid JSON format. Only one key-value pair expected.")

                except Exception as e:
                    print("Decryption error:", e)
                    messagebox.showerror("ERROR", "Decryption failed: " + str(e))

            else:
                messagebox.showerror("ERROR", "INVALID PASSWORD!")

        else:
            messagebox.showerror("ERROR", "INVALID PASSWORD ENTERED!")

    def Encrypt_File(self):
        File_Path = filedialog.askopenfilename(title="Select A File To Encrypt")

        if File_Path:
            Password = self.Password_Entry.get().strip()

            if Password.isascii() and len(Password) >= 8:
                Hash = sha3_512()
                Hash.update(b64encode(Password.encode("utf-8")))
                Password_Hash = Hash.hexdigest()

                if Password_Hash == self.__Stored_Password_Hash:
                    with open(File_Path, "rb") as ReadFile:
                        File_Data = ReadFile.read()
                        Key = self.__Generate_Encryption_Key()
                        FerNet = Fernet(Key)

                        Encrypted_Data = FerNet.encrypt(File_Data)

                        with open(File_Path, "wb") as WriteFile:
                            WriteFile.write(Encrypted_Data)

                        self.__File_Keys_Dict[File_Path] = Key.decode("utf-8")
                        self.__Write_File_Keys()

                        messagebox.showinfo("SUCCESS", "FILE ENCRYPTED SUCCESSFULLY!")

                else:
                    messagebox.showerror("ERROR", "INVALID PASSWORD!")

            else:
                messagebox.showerror(
                    "ERROR",
                    "INVALID PASSWORD ENTERED!\nPLEASE ENTER A PASSWORD OF AT LEAST 8 CHARACTERS CONTAINING LETTERS SYMBOLS AND NUMBERS!"
                )

    def Decrypt_File(self):
        File_Path = filedialog.askopenfilename(title="Select A File To Decrypt")

        if File_Path:
            Password = self.Password_Entry.get().strip()

            if Password.isascii() and len(Password) >= 8:
                Hash = sha3_512()
                Hash.update(b64encode(Password.encode("utf-8")))
                Password_Hash = Hash.hexdigest()

                if Password_Hash == self.__Stored_Password_Hash:
                    try:
                        with open(File_Path, "rb") as ReadFile:
                            File_Data = ReadFile.read()
                            Key = self.__File_Keys_Dict[File_Path]
                            FerNet = Fernet(Key.encode("utf-8"))

                            Decrypted_Data = FerNet.decrypt(File_Data)

                            with open(File_Path, "wb") as WriteFile:
                                WriteFile.write(Decrypted_Data)

                            messagebox.showinfo("SUCCESS", "FILE DECRYPTED SUCCESSFULLY!")

                    except Exception as e:
                        messagebox.showerror("ERROR", "INVALID FILE DATA!")

                else:
                    messagebox.showerror("ERROR", "INVALID PASSWORD!")

            else:
                messagebox.showerror("ERROR", "INVALID PASSWORD ENTERED!")


if __name__ == "__main__":
    Initializer = Hasher()
    Initializer.mainloop()
