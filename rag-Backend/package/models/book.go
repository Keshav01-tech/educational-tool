package models

import (
	"github.com/keshav/bookstore/package/config"
	"gorm.io/gorm"
)

var DB *gorm.DB

type Book struct {
	gorm.Model
	Name        string `json:"name"`
	Author      string `json:"author"`
	Publication string `json:"publication"`
}

func Init() {
	config.Connect()
	DB = config.GetDB()
	DB.AutoMigrate(&Book{})
}

func (b *Book) CreateBook() *Book {
	DB.Create(b)
	return b
}

func GetAllBooks() []Book {
	var books []Book
	DB.Find(&books)
	return books
}

func GetBookById(Id int64) (*Book, *gorm.DB) {
	var book Book

	result := DB.Where("id = ?", Id).First(&book)

	return &book, result
}

func DeleteBook(Id int64) *Book {
	var book Book

	DB.Where("id = ?", Id).First(&book)
	DB.Delete(&book)

	return &book
}
